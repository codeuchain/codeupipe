/**
 * platform.js — CUP Platform core library.
 *
 * Runs on the GitHub Pages site.  Detects the CUP extension,
 * communicates via window.cupBridge, and provides the platform API
 * to the dashboard, store, and other page components.
 *
 * CUP/TS pattern: This is a Pipeline orchestrator — it runs
 * detection filters, then exposes an API built on CUP Payload.
 */

const CupPlatform = (function() {
  'use strict';

  // ── State ───────────────────────────────────────────────────────

  const _state = {
    extensionDetected: false,
    tier: 'checking',
    device: 'unknown',
    capabilities: [],
    nativeAlive: false,
    httpAlive: false,
    recipes: null,
    installedCapabilities: [],
    statusCallbacks: [],
  };

  // ── CUP Payload (micro-port for page context) ─────────────────

  class Payload {
    constructor(data = {}) { this._data = { ...data }; }
    get(key, d) { return this._data[key] !== undefined ? this._data[key] : d; }
    insert(key, value) { return new Payload({ ...this._data, [key]: value }); }
    toDict() { return { ...this._data }; }
  }

  // ── Detection Pipeline ────────────────────────────────────────

  async function detectExtension() {
    // Filter 1: Check for window.cupBridge (injected by content script)
    if (window.cupBridge && window.cupBridge.detected) {
      _state.extensionDetected = true;
      try {
        const resp = await window.cupBridge.status();
        if (resp && resp.result) {
          _state.tier = resp.result.tier || 'wasm';
          _state.device = resp.result.device || 'unknown';
          _state.capabilities = resp.result.capabilities || [];
          _state.nativeAlive = resp.result.nativeAlive || false;
          _state.httpAlive = resp.result.httpAlive || false;
        }
      } catch {
        _state.tier = 'extension-error';
      }
      _notifyStatus();
      return;
    }

    // Filter 2: Wait for content script injection (up to 2s with retries)
    for (let i = 0; i < 4; i++) {
      await new Promise(r => setTimeout(r, 500));
      if (window.cupBridge && window.cupBridge.detected) {
        _state.extensionDetected = true;
        _state.tier = 'extension-pending';
        _notifyStatus();
        return;
      }
    }

    // Filter 3: Try direct HTTP to localhost (no extension)
    try {
      const resp = await fetch('http://localhost:8089/health', {
        signal: AbortSignal.timeout(2000),
      });
      const data = await resp.json();
      if (data.status === 'alive') {
        _state.httpAlive = true;
        _state.tier = 'http-direct';
        _state.device = data.device || 'unknown';
        return;
      }
    } catch { /* no localhost server */ }

    // Filter 4: Fallback — no extension, no server
    _state.tier = 'no-extension';
  }

  // ── Recipe Loading ────────────────────────────────────────────

  async function loadRecipes() {
    try {
      const resp = await fetch('recipes/manifest.json');
      _state.recipes = await resp.json();
    } catch {
      // Fallback: inline recipes for dev
      _state.recipes = { version: '1.0.0', capabilities: [] };
    }
    return _state.recipes;
  }

  // ── Status Subscription ───────────────────────────────────────

  function onStatus(callback) {
    _state.statusCallbacks.push(callback);
    // If extension detected, hook into its status stream
    if (window.cupBridge) {
      window.cupBridge.onStatus((status) => {
        _state.tier = status.tier;
        _state.device = status.device;
        _state.capabilities = status.capabilities || [];
        _state.nativeAlive = status.nativeAlive;
        _state.httpAlive = status.httpAlive;
        _notifyStatus();
      });
    }
  }

  function _notifyStatus() {
    const snapshot = { ..._state };
    delete snapshot.statusCallbacks;
    delete snapshot.recipes;
    for (const cb of _state.statusCallbacks) {
      try { cb(snapshot); } catch { /* ignore */ }
    }
  }

  // ── Provision ─────────────────────────────────────────────────

  async function provision(recipeId, onProgress) {
    if (!_state.extensionDetected) {
      throw new Error('Extension not detected. Install the CUP Platform Bridge extension.');
    }

    // Load recipe
    let recipe;
    try {
      const resp = await fetch(`recipes/${recipeId}.json`);
      recipe = await resp.json();
    } catch (e) {
      throw new Error(`Failed to load recipe: ${recipeId}`);
    }

    if (onProgress) onProgress({ phase: 'start', recipe: recipe.id });

    // Send to extension for execution
    const result = await window.cupBridge.provision(recipe, recipe.tier);

    if (onProgress) onProgress({ phase: 'complete', result: result.result });

    // Track as installed if successful, or if WASM fallback for a wasm-tier recipe
    const isSuccess = result.result && result.result.success;
    const isWasmAvailable = result.result
      && result.result.status === 'wasm-fallback'
      && recipe.tier === 'wasm';

    if (isSuccess || isWasmAvailable) {
      if (!_state.installedCapabilities.includes(recipeId)) {
        _state.installedCapabilities.push(recipeId);
      }
      _notifyStatus();
    }

    return result;
  }

  // ── Delegate ──────────────────────────────────────────────────

  async function delegate(path, body, opts) {
    if (_state.extensionDetected && window.cupBridge) {
      return window.cupBridge.delegate(path, body, opts);
    }

    // Fallback: direct HTTP
    if (_state.httpAlive) {
      const method = (opts && opts.method) || 'POST';
      const fetchOpts = { method, headers: { 'Accept': 'application/json' } };
      if (body) {
        fetchOpts.headers['Content-Type'] = 'application/json';
        fetchOpts.body = JSON.stringify(body);
      }
      const resp = await fetch(`http://localhost:8089${path}`, fetchOpts);
      return { result: await resp.json(), tier: 'http-direct' };
    }

    return { result: null, tier: 'disconnected', error: 'No compute available' };
  }

  // ── Public API ────────────────────────────────────────────────

  return {
    // Detection
    detect: detectExtension,
    get detected() { return _state.extensionDetected; },
    get tier() { return _state.tier; },
    get device() { return _state.device; },
    get capabilities() { return [..._state.capabilities]; },
    get nativeAlive() { return _state.nativeAlive; },
    get httpAlive() { return _state.httpAlive; },
    get state() { return { ..._state, statusCallbacks: undefined, recipes: undefined }; },

    // Recipes
    loadRecipes,
    get recipes() { return _state.recipes; },
    get installed() { return [..._state.installedCapabilities]; },

    // Actions
    provision,
    delegate,
    onStatus,

    // Convenience
    ping: () => window.cupBridge ? window.cupBridge.ping() : Promise.resolve(null),
    probe: () => window.cupBridge ? window.cupBridge.probe() : Promise.resolve(null),
    exec: (cmd) => window.cupBridge ? window.cupBridge.exec(cmd) : Promise.reject(new Error('No extension')),
    start: (port) => window.cupBridge ? window.cupBridge.start(port) : Promise.reject(new Error('No extension')),

    // Payload class for page-level pipelines
    Payload,
  };
})();

// Auto-detect on load
if (typeof window !== 'undefined') {
  window.CupPlatform = CupPlatform;

  // Listen for late extension injection
  window.addEventListener('cup-bridge-ready', async () => {
    await CupPlatform.detect();
  });
}
