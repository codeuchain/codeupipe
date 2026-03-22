/**
 * bridge.js — Generic browser↔desktop bridge client.
 *
 * Drop this into any dashboard to auto-discover and delegate work
 * to native compute running on localhost (or LAN / remote).
 *
 * Architecture:
 *   Browser (this code)
 *     ├─ Tier 0: CUP Extension   ← Chrome extension + Native Messaging
 *     ├─ Tier 1: localhost:8089  ← native GPU, full PyTorch
 *     ├─ Tier 2: LAN host       ← another machine on same network
 *     ├─ Tier 3: Remote server   ← cloud/VPS
 *     └─ Tier 4: WASM fallback   ← browser-only, WebWorker
 *
 * Usage:
 *   <script src="bridge.js"></script>
 *   <script>
 *     const bridge = new Bridge({ ports: [8089, 8090] });
 *     await bridge.probe();
 *     if (bridge.alive) {
 *       const result = await bridge.post('/dream-train', { model_name: '...' });
 *     } else {
 *       // Fall back to WASM worker
 *     }
 *   </script>
 *
 * Configuration:
 *   new Bridge({
 *     ports: [8089],                    // Localhost ports to scan
 *     remoteHosts: ['gpu.example.com'], // Extra hosts to probe
 *     healthPath: '/health',            // Health endpoint path
 *     probeTimeout: 3000,               // Probe timeout (ms)
 *     secret: '',                       // Shared secret header
 *     requiredCapabilities: [],         // Required caps filter
 *     autoProbe: true,                  // Probe on first request
 *     onTierChange: (tier) => {},       // Callback on tier change
 *     onStatusChange: (status) => {},   // Callback on status change
 *     retryInterval: 30000,             // Re-probe interval (ms) when disconnected
 *   });
 *
 * Events (via onStatusChange callback):
 *   { alive: true,  tier: 'local', device: 'mps', latency: 12, capabilities: [...] }
 *   { alive: false, tier: 'wasm',  device: 'wasm', error: 'Connection refused' }
 *
 * Zero dependencies. Pure vanilla JS. Works in any modern browser.
 */

class Bridge {
  /**
   * @param {Object} opts
   * @param {number[]} [opts.ports=[8089]] - Localhost ports to scan.
   * @param {string[]} [opts.remoteHosts=[]] - Extra host:port strings to probe.
   * @param {string} [opts.healthPath='/health'] - Health endpoint path.
   * @param {number} [opts.probeTimeout=3000] - Per-probe timeout in ms.
   * @param {string} [opts.secret=''] - Shared secret for X-Spore-Secret header.
   * @param {string[]} [opts.requiredCapabilities=[]] - Required capabilities.
   * @param {boolean} [opts.autoProbe=true] - Auto-probe on first request.
   * @param {Function} [opts.onTierChange] - Called when active tier changes.
   * @param {Function} [opts.onStatusChange] - Called on any status change.
   * @param {number} [opts.retryInterval=30000] - Re-probe interval when disconnected (ms).
   */
  constructor(opts = {}) {
    this.ports = opts.ports || [8089];
    this.remoteHosts = opts.remoteHosts || [];
    this.healthPath = opts.healthPath || '/health';
    this.probeTimeout = opts.probeTimeout || 3000;
    this.secret = opts.secret || '';
    this.requiredCapabilities = opts.requiredCapabilities || [];
    this.autoProbe = opts.autoProbe !== undefined ? opts.autoProbe : true;
    this.onTierChange = opts.onTierChange || null;
    this.onStatusChange = opts.onStatusChange || null;
    this.retryInterval = opts.retryInterval || 30000;

    // State
    this._endpoints = [];
    this._active = null;
    this._probed = false;
    this._retryTimer = null;
  }

  // ── Properties ──────────────────────────────────────────────────

  /** @returns {boolean} Whether a live endpoint is connected. */
  get alive() { return this._active !== null && this._active.alive; }

  /** @returns {string} Active tier: 'local', 'lan', 'remote', or 'wasm'. */
  get tier() { return this._active?.tier || 'wasm'; }

  /** @returns {string} Active device: 'cuda', 'mps', 'cpu', or 'wasm'. */
  get device() { return this._active?.device || 'wasm'; }

  /** @returns {string[]} Active endpoint capabilities. */
  get capabilities() { return this._active?.capabilities || []; }

  /** @returns {string} Base URL of active endpoint, or ''. */
  get baseUrl() { return this._active?.baseUrl || ''; }

  /** @returns {number} Latency to active endpoint in ms. */
  get latency() { return this._active?.latency || 0; }

  /** @returns {Object[]} All discovered endpoints. */
  get endpoints() { return [...this._endpoints]; }

  // ── Probe & Connect ─────────────────────────────────────────────

  /**
   * Probe all configured endpoints and select the best one.
   * @returns {Promise<Object[]>} Array of endpoint status objects.
   */
  async probe() {
    // ── Tier 0: CUP Extension (best possible — native messaging) ──
    const extensionEndpoint = await this._probeExtension();

    const configs = this._buildConfigs();
    const results = await Promise.allSettled(
      configs.map(cfg => this._probeOne(cfg))
    );

    this._endpoints = [];

    // Extension endpoint first (tier 0)
    if (extensionEndpoint) {
      this._endpoints.push(extensionEndpoint);
    }

    // Then HTTP endpoints
    for (let i = 0; i < results.length; i++) {
      const r = results[i];
      this._endpoints.push(
        r.status === 'fulfilled' ? r.value : {
          ...configs[i], alive: false, error: r.reason?.message || 'Probe failed',
        }
      );
    }

    const oldTier = this.tier;
    this._selectActive();
    this._probed = true;

    if (this.tier !== oldTier && this.onTierChange) {
      this.onTierChange(this.tier, oldTier);
    }
    if (this.onStatusChange) {
      this.onStatusChange(this.status());
    }

    // Start retry timer if disconnected
    if (!this.alive && this.retryInterval > 0) {
      this._startRetry();
    } else {
      this._stopRetry();
    }

    return this._endpoints;
  }

  /**
   * Probe and connect — convenience method.
   * @returns {Promise<boolean>} True if a live endpoint was found.
   */
  async connect() {
    await this.probe();
    return this.alive;
  }

  /**
   * Stop retry probing.
   */
  disconnect() {
    this._stopRetry();
    this._active = null;
    this._probed = false;
  }

  // ── Request / Delegate ──────────────────────────────────────────

  /**
   * GET request to the active endpoint.
   * @param {string} path - URL path (e.g. '/swarm-status').
   * @param {Object} [opts] - Extra fetch options.
   * @returns {Promise<Object>} Parsed JSON response.
   */
  async get(path, opts = {}) {
    return this._request(path, 'GET', null, opts);
  }

  /**
   * POST request to the active endpoint.
   * @param {string} path - URL path (e.g. '/dream-train').
   * @param {Object} body - JSON body.
   * @param {Object} [opts] - Extra fetch options.
   * @returns {Promise<Object>} Parsed JSON response.
   */
  async post(path, body, opts = {}) {
    return this._request(path, 'POST', body, opts);
  }

  /**
   * Delegate work to the best available compute tier.
   * Falls back gracefully: local → LAN → remote → error.
   *
   * @param {string} path - Endpoint path.
   * @param {Object} body - Request body.
   * @param {Object} [opts] - Extra options.
   * @returns {Promise<{response: Object, tier: string, device: string}>}
   */
  async delegate(path, body, opts = {}) {
    if (!this._probed && this.autoProbe) {
      await this.probe();
    }

    if (!this.alive) {
      return {
        response: null,
        tier: 'wasm',
        device: 'wasm',
        alive: false,
        error: 'No bridge endpoint available',
      };
    }

    try {
      const response = await this.post(path, body, opts);
      return {
        response,
        tier: this.tier,
        device: this.device,
        alive: true,
      };
    } catch (err) {
      // Mark endpoint as dead and try re-probe
      if (this._active) this._active.alive = false;
      this._selectActive();

      // If we found another endpoint, retry once
      if (this.alive) {
        try {
          const response = await this.post(path, body, opts);
          return { response, tier: this.tier, device: this.device, alive: true };
        } catch (retryErr) {
          // Give up
        }
      }

      return {
        response: null,
        tier: 'wasm',
        device: 'wasm',
        alive: false,
        error: err.message,
      };
    }
  }

  // ── Status ──────────────────────────────────────────────────────

  /**
   * Full bridge status for dashboards.
   * @returns {Object}
   */
  status() {
    return {
      alive: this.alive,
      tier: this.tier,
      device: this.device,
      capabilities: this.capabilities,
      baseUrl: this.baseUrl,
      latency: this.latency,
      probed: this._probed,
      endpoints: this._endpoints.map(ep => ({
        name: ep.name,
        tier: ep.tier,
        alive: ep.alive,
        baseUrl: ep.baseUrl,
        device: ep.device || 'unknown',
        latency: ep.latency || 0,
        capabilities: ep.capabilities || [],
        error: ep.error || '',
      })),
    };
  }

  /**
   * Check if active endpoint has a specific capability.
   * @param {string} cap
   * @returns {boolean}
   */
  hasCapability(cap) {
    return this.capabilities.includes(cap);
  }

  // ── Internal ────────────────────────────────────────────────────

  /**
   * Probe for CUP Extension (tier 0) via window.cupBridge.
   * @returns {Promise<Object|null>} Extension endpoint or null.
   */
  async _probeExtension() {
    if (typeof window === 'undefined') return null;
    if (!window.cupBridge || !window.cupBridge.detected) return null;

    try {
      const t0 = performance.now();
      const resp = await window.cupBridge.status();
      const latency = Math.round(performance.now() - t0);

      if (!resp || !resp.result) {
        return {
          name: 'extension',
          tier: 'extension',
          baseUrl: 'extension://cup-bridge',
          alive: true,
          latency,
          device: 'unknown',
          capabilities: [],
          metadata: resp,
        };
      }

      const r = resp.result;
      const capabilities = r.capabilities || [];
      return {
        name: 'extension',
        tier: 'extension',
        baseUrl: 'extension://cup-bridge',
        alive: true,
        latency,
        device: r.device || 'unknown',
        capabilities,
        metadata: r,
        nativeAlive: r.nativeAlive || false,
        httpAlive: r.httpAlive || false,
      };
    } catch {
      return {
        name: 'extension',
        tier: 'extension',
        baseUrl: 'extension://cup-bridge',
        alive: false,
        latency: 0,
        error: 'Extension probe failed',
      };
    }
  }

  _buildConfigs() {
    const configs = [];

    // Localhost ports
    for (const port of this.ports) {
      configs.push({
        name: `local-${port}`,
        tier: 'local',
        baseUrl: `http://localhost:${port}`,
        healthUrl: `http://localhost:${port}${this.healthPath}`,
      });
      // Also try 127.0.0.1 (some browsers treat localhost differently)
      configs.push({
        name: `local-ip-${port}`,
        tier: 'local',
        baseUrl: `http://127.0.0.1:${port}`,
        healthUrl: `http://127.0.0.1:${port}${this.healthPath}`,
      });
    }

    // Remote hosts
    for (const host of this.remoteHosts) {
      const url = host.includes('://') ? host : `http://${host}`;
      const isLocal = host.includes('localhost') || host.includes('127.0.0.1');
      configs.push({
        name: `remote-${host}`,
        tier: isLocal ? 'local' : 'remote',
        baseUrl: url,
        healthUrl: `${url}${this.healthPath}`,
      });
    }

    return configs;
  }

  async _probeOne(config) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.probeTimeout);

    const headers = { 'Accept': 'application/json' };
    if (this.secret) headers['X-Spore-Secret'] = this.secret;

    try {
      const t0 = performance.now();
      const resp = await fetch(config.healthUrl, {
        method: 'GET',
        headers,
        signal: controller.signal,
      });
      const latency = performance.now() - t0;
      clearTimeout(timer);

      if (!resp.ok) {
        return { ...config, alive: false, latency, error: `HTTP ${resp.status}` };
      }

      const data = await resp.json();
      const capabilities = [];
      if (data.torch_version) capabilities.push('torch');
      if (data.cuda) capabilities.push('cuda');
      if (data.mps) capabilities.push('mps');
      if (data.swarm !== undefined) capabilities.push('swarm');
      if (data.queue !== undefined) capabilities.push('queue');
      if (Array.isArray(data.capabilities)) capabilities.push(...data.capabilities);

      return {
        ...config,
        alive: true,
        latency: Math.round(latency),
        device: data.device || 'unknown',
        capabilities: [...new Set(capabilities)],
        metadata: data,
      };
    } catch (err) {
      clearTimeout(timer);
      return {
        ...config,
        alive: false,
        latency: 0,
        error: err.name === 'AbortError' ? 'Timeout' : err.message,
      };
    }
  }

  _selectActive() {
    const TIER_ORDER = { extension: 0, local: 1, lan: 2, remote: 3, wasm: 4 };

    let candidates = this._endpoints.filter(ep => ep.alive);

    // Filter by required capabilities
    if (this.requiredCapabilities.length > 0) {
      candidates = candidates.filter(ep =>
        this.requiredCapabilities.every(cap =>
          (ep.capabilities || []).includes(cap)
        )
      );
    }

    // Deduplicate — keep lowest-latency per base URL
    const byUrl = {};
    for (const ep of candidates) {
      const existing = byUrl[ep.baseUrl];
      if (!existing || (ep.latency || 0) < (existing.latency || 0)) {
        byUrl[ep.baseUrl] = ep;
      }
    }
    candidates = Object.values(byUrl);

    if (candidates.length === 0) {
      this._active = null;
      return;
    }

    // Sort: tier rank → latency
    candidates.sort((a, b) => {
      const ta = TIER_ORDER[a.tier] ?? 3;
      const tb = TIER_ORDER[b.tier] ?? 3;
      if (ta !== tb) return ta - tb;
      return (a.latency || 0) - (b.latency || 0);
    });

    this._active = candidates[0];
  }

  async _request(path, method, body, opts = {}) {
    if (!this._probed && this.autoProbe) {
      await this.probe();
    }

    if (!this.alive) {
      throw new Error('No active bridge endpoint. Call probe() first.');
    }

    // Extension tier: delegate through window.cupBridge
    if (this.tier === 'extension' && typeof window !== 'undefined' && window.cupBridge) {
      const resp = await window.cupBridge.delegate(path, body, { method, ...opts });
      if (resp && resp.result) return resp.result;
      if (resp && resp.error) throw new Error(resp.error);
      return resp;
    }

    const url = `${this.baseUrl}${path}`;
    const headers = {
      'Accept': 'application/json',
      ...(opts.headers || {}),
    };
    if (this.secret) headers['X-Spore-Secret'] = this.secret;

    const fetchOpts = { method, headers };
    if (body !== null && body !== undefined) {
      headers['Content-Type'] = 'application/json';
      fetchOpts.body = JSON.stringify(body);
    }

    const resp = await fetch(url, fetchOpts);
    if (!resp.ok) {
      let errBody;
      try { errBody = await resp.json(); } catch { errBody = { error: resp.statusText }; }
      throw new Error(errBody.error || `HTTP ${resp.status}`);
    }

    return resp.json();
  }

  _startRetry() {
    if (this._retryTimer) return;
    this._retryTimer = setInterval(() => {
      this.probe().catch(() => {});
    }, this.retryInterval);
  }

  _stopRetry() {
    if (this._retryTimer) {
      clearInterval(this._retryTimer);
      this._retryTimer = null;
    }
  }
}


// ── UI Widget (optional) ────────────────────────────────────────────
//
// A small status indicator that shows the current bridge tier.
// Embed it in your dashboard:
//
//   const widget = Bridge.createWidget(bridge, document.getElementById('bridge-status'));
//
// It auto-updates when the bridge status changes.

Bridge.createWidget = function(bridge, container) {
  if (!container) return null;

  const TIER_ICONS = {
    extension: '🔌',
    local:  '🖥️',
    lan:    '🌐',
    remote: '☁️',
    wasm:   '⚡',
  };

  const TIER_LABELS = {
    extension: 'Extension Bridge',
    local:  'Local GPU',
    lan:    'LAN Compute',
    remote: 'Remote Server',
    wasm:   'Browser Only',
  };

  const TIER_COLORS = {
    extension: '#bc8cff',
    local:  '#3fb950',
    lan:    '#58a6ff',
    remote: '#d29922',
    wasm:   '#8b949e',
  };

  function render(status) {
    const icon = TIER_ICONS[status.tier] || '❓';
    const label = TIER_LABELS[status.tier] || status.tier;
    const color = TIER_COLORS[status.tier] || '#8b949e';
    const dot = status.alive ? '🟢' : '🔴';
    const device = status.device !== 'wasm' ? ` (${status.device})` : '';
    const latencyStr = status.latency > 0 ? ` ${status.latency}ms` : '';

    container.innerHTML = `
      <span style="display:inline-flex;align-items:center;gap:6px;
                    padding:4px 10px;border-radius:4px;
                    background:rgba(${hexToRgb(color)},0.15);
                    border:1px solid ${color};font-size:0.8rem;
                    font-family:monospace;color:${color};">
        ${dot} ${icon} ${label}${device}${latencyStr}
      </span>
    `;
  }

  function hexToRgb(hex) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `${r},${g},${b}`;
  }

  // Initial render
  render(bridge.status());

  // Hook into status changes
  const origCallback = bridge.onStatusChange;
  bridge.onStatusChange = function(status) {
    render(status);
    if (origCallback) origCallback(status);
  };

  return { render, bridge };
};


// Export for modules and global scope
if (typeof module !== 'undefined' && module.exports) {
  module.exports = Bridge;
} else if (typeof window !== 'undefined') {
  window.Bridge = Bridge;
}
