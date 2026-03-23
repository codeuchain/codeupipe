/**
 * service-worker.js — Extension background service worker.
 *
 * This is a CUP/TS-style pipeline running in the Chrome extension
 * background.  Every request from the content script flows through:
 *
 *   ParseRequest → SelectTier → [NativeRelay | HttpProxy | WasmFallback] → FormatResponse
 *
 * Each "filter" is a plain function: (payload) → payload.
 * Payload is an immutable object mirroring CUP Payload.insert().
 *
 * Zero dependencies.  Pure Chrome APIs + fetch.
 */

// ── CUP Payload (micro-port for service worker context) ─────────────

class Payload {
  constructor(data = {}) {
    this._data = { ...data };
  }
  get(key, defaultVal = undefined) {
    return this._data[key] !== undefined ? this._data[key] : defaultVal;
  }
  insert(key, value) {
    return new Payload({ ...this._data, [key]: value });
  }
  toDict() {
    return { ...this._data };
  }
}

// ── State ───────────────────────────────────────────────────────────

const state = {
  nativePort: null,        // chrome.runtime.connectNative port
  nativeAlive: false,      // whether native host responded
  httpAlive: false,         // whether localhost HTTP responded
  capabilities: [],         // from last health check
  device: 'unknown',
  tier: 'disconnected',    // extension-native | extension-http | wasm | disconnected
  lastProbe: 0,
  config: {
    nativeHostName: 'com.codeupipe.bridge',
    httpPort: 8089,
    healthPath: '/health',
    probeInterval: 30000,
  },
};

// ── Filters (CUP pattern: each does ONE thing) ─────────────────────

/**
 * ParseRequestFilter — extract action, path, body from the raw message.
 */
function parseRequest(payload) {
  const msg = payload.get('raw_message', {});
  return payload
    .insert('action', msg.action || 'unknown')
    .insert('request_id', msg.id || '')
    .insert('path', msg.path || '/health')
    .insert('body', msg.body || null)
    .insert('method', msg.method || 'GET')
    .insert('capability', msg.capability || '')
    .insert('prefer_tier', msg.preferTier || '');
}

/**
 * SelectTierFilter — determine best available tier for this request.
 *
 * For provision requests the recipe may specify its own tier (native,
 * http, or wasm).  We honour that hint when the preferred transport is
 * available, and fall through gracefully otherwise.
 */
function selectTier(payload) {
  const action = payload.get('action');
  const preferTier = payload.get('prefer_tier', '');

  // Internal actions always go through specific handlers
  if (['ping', 'status', 'get-config', 'set-config'].includes(action)) {
    return payload.insert('tier', 'internal');
  }

  // Provision / exec — respect the recipe's preferred tier, then
  // auto-select the best *available* transport.
  if (['provision', 'exec', 'start', 'stop', 'configure'].includes(action)) {
    // Caller can set prefer_tier to the recipe's tier field
    if (preferTier === 'native' && state.nativeAlive) {
      return payload.insert('tier', 'native');
    }
    if (preferTier === 'http' && state.httpAlive) {
      return payload.insert('tier', 'http');
    }
    if (preferTier === 'wasm') {
      return payload.insert('tier', 'wasm');
    }

    // Auto-select best available
    if (state.nativeAlive) return payload.insert('tier', 'native');
    if (state.httpAlive) return payload.insert('tier', 'http');
    return payload.insert('tier', 'wasm');
  }

  // Prefer native messaging if alive
  if (preferTier === 'native' && state.nativeAlive) {
    return payload.insert('tier', 'native');
  }

  // Auto-select best tier
  if (state.nativeAlive) return payload.insert('tier', 'native');
  if (state.httpAlive) return payload.insert('tier', 'http');
  return payload.insert('tier', 'wasm');
}

/**
 * InternalHandlerFilter — handle extension-internal actions.
 */
function handleInternal(payload) {
  if (payload.get('tier') !== 'internal') return payload;

  const action = payload.get('action');

  if (action === 'ping') {
    return payload.insert('response', {
      status: 'pong',
      extension: 'cup-platform-bridge',
      version: '1.0.0',
      tier: state.tier,
      nativeAlive: state.nativeAlive,
      httpAlive: state.httpAlive,
      device: state.device,
      capabilities: state.capabilities,
    });
  }

  if (action === 'status') {
    return payload.insert('response', {
      status: 'ok',
      tier: state.tier,
      nativeAlive: state.nativeAlive,
      httpAlive: state.httpAlive,
      device: state.device,
      capabilities: state.capabilities,
      lastProbe: state.lastProbe,
      config: state.config,
    });
  }

  if (action === 'get-config') {
    return payload.insert('response', {
      status: 'ok',
      config: state.config,
    });
  }

  if (action === 'set-config') {
    const body = payload.get('body', {});
    Object.assign(state.config, body);
    chrome.storage.local.set({ cupConfig: state.config });
    return payload.insert('response', {
      status: 'ok',
      config: state.config,
    });
  }

  return payload.insert('response', { error: `Unknown internal action: ${action}` });
}

/**
 * NativeRelayFilter — relay request to native messaging host.
 */
async function nativeRelay(payload) {
  if (payload.get('tier') !== 'native') return payload;
  if (payload.get('response')) return payload;  // already handled

  const action = payload.get('action');
  const msg = payload.get('raw_message', {});

  try {
    const response = await sendNativeMessage({
      action,
      ...msg,
    });
    return payload
      .insert('response', response)
      .insert('response_tier', 'extension-native');
  } catch (err) {
    // Native messaging failed — mark as dead, fall through to HTTP/WASM
    state.nativeAlive = false;
    state.tier = state.httpAlive ? 'extension-http' : 'wasm';

    // Fall through to next filter for any action (HTTP or WASM can handle it)
    return payload
      .insert('tier', state.httpAlive ? 'http' : 'wasm')
      .insert('native_error', err.message);
  }
}

/**
 * HttpProxyFilter — proxy request to localhost spore_runner via fetch.
 */
async function httpProxy(payload) {
  if (payload.get('tier') !== 'http') return payload;
  if (payload.get('response')) return payload;

  const method = payload.get('method', 'GET');
  const path = payload.get('path', '/health');
  const body = payload.get('body');
  const port = state.config.httpPort;
  const url = `http://localhost:${port}${path}`;

  try {
    const fetchOpts = {
      method,
      headers: { 'Accept': 'application/json' },
    };
    if (body) {
      fetchOpts.headers['Content-Type'] = 'application/json';
      fetchOpts.body = JSON.stringify(body);
    }

    const resp = await fetch(url, fetchOpts);
    const data = await resp.json();

    return payload
      .insert('response', { status: 'ok', data })
      .insert('response_tier', 'extension-http');
  } catch (err) {
    state.httpAlive = false;
    return payload.insert('response', {
      error: `HTTP proxy failed: ${err.message}`,
      tier: 'wasm',
    });
  }
}

/**
 * WasmFallbackFilter — report that we need browser WASM fallback.
 */
function wasmFallback(payload) {
  if (payload.get('response')) return payload;

  return payload.insert('response', {
    status: 'wasm-fallback',
    tier: 'wasm',
    message: 'No native or HTTP compute available. Use browser WASM.',
    device: 'wasm',
  }).insert('response_tier', 'wasm');
}

/**
 * FormatResponseFilter — normalize response for content script.
 */
function formatResponse(payload) {
  const response = payload.get('response', {});
  const requestId = payload.get('request_id', '');
  const responseTier = payload.get('response_tier', state.tier);

  return payload.insert('final_response', {
    type: 'cup-response',
    id: requestId,
    result: response,
    tier: responseTier,
    device: state.device,
    timestamp: Date.now(),
  });
}

// ── Pipeline runner ─────────────────────────────────────────────────

async function runPipeline(rawMessage) {
  let payload = new Payload({ raw_message: rawMessage });

  // Sync filters
  payload = parseRequest(payload);
  payload = selectTier(payload);
  payload = handleInternal(payload);

  // Async filters (may hit network)
  payload = await nativeRelay(payload);
  payload = await httpProxy(payload);

  // Final sync filters
  payload = wasmFallback(payload);
  payload = formatResponse(payload);

  return payload.get('final_response');
}

// ── Native Messaging helpers ────────────────────────────────────────

function sendNativeMessage(msg) {
  return new Promise((resolve, reject) => {
    try {
      chrome.runtime.sendNativeMessage(
        state.config.nativeHostName,
        msg,
        (response) => {
          if (chrome.runtime.lastError) {
            reject(new Error(chrome.runtime.lastError.message));
          } else {
            resolve(response);
          }
        }
      );
    } catch (err) {
      reject(err);
    }
  });
}

// ── Probe / Health Check ────────────────────────────────────────────

async function probe() {
  // 1. Try native messaging
  try {
    const nativeResp = await sendNativeMessage({ action: 'health' });
    state.nativeAlive = true;
    if (nativeResp.device) state.device = nativeResp.device;
    if (nativeResp.status === 'alive' || nativeResp.status === 'ok') {
      // Extract capabilities
      const caps = [];
      if (nativeResp.torch_version) caps.push('torch');
      if (nativeResp.cuda) caps.push('cuda');
      if (nativeResp.mps) caps.push('mps');
      if (nativeResp.swarm !== undefined) caps.push('swarm');
      if (nativeResp.queue !== undefined) caps.push('queue');
      state.capabilities = caps;
    }
  } catch {
    state.nativeAlive = false;
  }

  // 2. Try HTTP localhost
  try {
    const port = state.config.httpPort;
    const resp = await fetch(`http://localhost:${port}/health`, {
      signal: AbortSignal.timeout(3000),
    });
    const data = await resp.json();
    state.httpAlive = data.status === 'alive';
    if (!state.nativeAlive && data.device) state.device = data.device;
  } catch {
    state.httpAlive = false;
  }

  // 3. Determine tier
  if (state.nativeAlive) state.tier = 'extension-native';
  else if (state.httpAlive) state.tier = 'extension-http';
  else state.tier = 'wasm';

  state.lastProbe = Date.now();

  // Push status to all connected pages
  broadcastStatus();
}

function broadcastStatus() {
  const statusMsg = {
    type: 'cup-status',
    tier: state.tier,
    nativeAlive: state.nativeAlive,
    httpAlive: state.httpAlive,
    device: state.device,
    capabilities: state.capabilities,
    lastProbe: state.lastProbe,
  };

  // Send to all content scripts
  chrome.tabs.query({}, (tabs) => {
    for (const tab of tabs) {
      try {
        chrome.tabs.sendMessage(tab.id, statusMsg);
      } catch {
        // Tab may not have content script
      }
    }
  });
}

// ── Message Listeners ───────────────────────────────────────────────

// From content scripts
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type !== 'cup-request') return false;

  runPipeline(message)
    .then(response => sendResponse(response))
    .catch(err => sendResponse({
      type: 'cup-response',
      id: message.id || '',
      result: { error: err.message },
      tier: 'error',
    }));

  return true; // async response
});

// From external pages (via externally_connectable)
chrome.runtime.onMessageExternal.addListener((message, sender, sendResponse) => {
  // Verify sender origin
  if (!sender.url || !sender.url.includes('codeuchain.github.io')) {
    sendResponse({ error: 'Unauthorized origin' });
    return false;
  }

  if (message.type !== 'cup-request') return false;

  runPipeline(message)
    .then(response => sendResponse(response))
    .catch(err => sendResponse({
      type: 'cup-response',
      id: message.id || '',
      result: { error: err.message },
      tier: 'error',
    }));

  return true;
});

// ── Lifecycle ───────────────────────────────────────────────────────

// Initial probe on install/startup
chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.get('cupConfig', (result) => {
    if (result.cupConfig) Object.assign(state.config, result.cupConfig);
    probe();
  });
});

chrome.runtime.onStartup.addListener(() => {
  chrome.storage.local.get('cupConfig', (result) => {
    if (result.cupConfig) Object.assign(state.config, result.cupConfig);
    probe();
  });
});

// Periodic re-probe
setInterval(() => probe(), state.config.probeInterval);
