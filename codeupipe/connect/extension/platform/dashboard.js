/**
 * dashboard.js — Live dashboard component.
 *
 * CUP/TS pattern: Filters transform Payload for each dashboard section.
 * Polls status and renders live device/tier/capability info.
 */

const CupDashboard = (function () {
  'use strict';

  const Payload = CupPlatform.Payload;
  let _pollInterval = null;

  // ── CUP Filters ────────────────────────────────────────────────

  function readStatusFilter(payload) {
    return payload
      .insert('tier', CupPlatform.tier)
      .insert('device', CupPlatform.device)
      .insert('nativeAlive', CupPlatform.nativeAlive)
      .insert('httpAlive', CupPlatform.httpAlive)
      .insert('capabilities', CupPlatform.capabilities)
      .insert('detected', CupPlatform.detected);
  }

  function renderTierFilter(payload) {
    const el = document.getElementById('dash-tier');
    if (!el) return payload;

    const tier = payload.get('tier', 'unknown');
    const labels = {
      native: '🟢 Native (Tier 0)',
      'extension-native': '🟢 Native via Extension',
      'extension-wasm': '🟡 WASM via Extension',
      http: '🔵 HTTP Localhost',
      'http-direct': '🔵 HTTP Direct',
      wasm: '🟡 WASM Only',
      'no-extension': '⚫ No Extension',
      checking: '⏳ Checking…',
      disconnected: '🔴 Disconnected',
    };
    el.textContent = labels[tier] || `❓ ${tier}`;
    el.className = `dash-tier tier-${tier}`;
    return payload;
  }

  function renderDeviceFilter(payload) {
    const el = document.getElementById('dash-device');
    if (!el) return payload;
    el.textContent = payload.get('device', '—');
    return payload;
  }

  function renderConnectionsFilter(payload) {
    const nativeEl = document.getElementById('dash-native');
    const httpEl = document.getElementById('dash-http');
    if (nativeEl) {
      const alive = payload.get('nativeAlive', false);
      nativeEl.textContent = alive ? '✅ Connected' : '❌ Not Connected';
      nativeEl.className = alive ? 'dash-status alive' : 'dash-status dead';
    }
    if (httpEl) {
      const alive = payload.get('httpAlive', false);
      httpEl.textContent = alive ? '✅ Connected' : '❌ Not Connected';
      httpEl.className = alive ? 'dash-status alive' : 'dash-status dead';
    }
    return payload;
  }

  function renderCapabilitiesFilter(payload) {
    const el = document.getElementById('dash-capabilities');
    if (!el) return payload;

    const caps = payload.get('capabilities', []);
    if (caps.length === 0) {
      el.innerHTML = '<span class="dash-empty">No capabilities installed</span>';
    } else {
      el.innerHTML = caps.map(c =>
        `<span class="dash-chip">${_esc(c)}</span>`
      ).join('');
    }
    return payload;
  }

  function renderExtensionFilter(payload) {
    const el = document.getElementById('dash-extension');
    if (!el) return payload;

    const detected = payload.get('detected', false);
    el.textContent = detected ? '✅ Installed' : '❌ Not Detected';
    el.className = detected ? 'dash-status alive' : 'dash-status dead';
    return payload;
  }

  // ── Pipeline ───────────────────────────────────────────────────

  function runPipeline() {
    let payload = new Payload({});

    const filters = [
      readStatusFilter,
      renderTierFilter,
      renderDeviceFilter,
      renderConnectionsFilter,
      renderCapabilitiesFilter,
      renderExtensionFilter,
    ];

    for (const f of filters) {
      payload = f(payload);
    }

    return payload;
  }

  // ── Lifecycle ──────────────────────────────────────────────────

  function start(intervalMs) {
    intervalMs = intervalMs || 5000;
    // Render immediately
    runPipeline();

    // Subscribe to live status pushes
    CupPlatform.onStatus(() => runPipeline());

    // Also poll as fallback
    _pollInterval = setInterval(runPipeline, intervalMs);
  }

  function stop() {
    if (_pollInterval) {
      clearInterval(_pollInterval);
      _pollInterval = null;
    }
  }

  function _esc(s) {
    const el = document.createElement('span');
    el.textContent = s;
    return el.innerHTML;
  }

  return { start, stop, refresh: runPipeline };
})();
