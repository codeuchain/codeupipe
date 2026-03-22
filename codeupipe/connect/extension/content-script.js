/**
 * content-script.js — Bridge between web page and CUP extension.
 *
 * Injected into Pages site and localhost dashboards.
 * Exposes `window.cupBridge` API to the page via a relay:
 *
 *   Page (window.postMessage) → Content Script → chrome.runtime.sendMessage → Service Worker
 *   Service Worker → chrome.runtime.onMessage → Content Script → window.postMessage → Page
 *
 * Also injects a tiny <script> that defines the window.cupBridge
 * object, so the page can call it directly without knowing about
 * postMessage internals.
 *
 * CUP pattern: This is a Tap — it observes messages flowing between
 * page and extension without modifying them.
 */

// ── Pending request correlation ─────────────────────────────────────

const pendingRequests = new Map();

// ── Page → Extension relay ──────────────────────────────────────────

window.addEventListener('message', (event) => {
  // Only accept messages from our page
  if (event.source !== window) return;
  if (!event.data || event.data.type !== 'cup-request') return;

  const msg = event.data;
  const requestId = msg.id || `req-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;

  // Forward to service worker
  chrome.runtime.sendMessage(
    { ...msg, id: requestId, type: 'cup-request' },
    (response) => {
      if (chrome.runtime.lastError) {
        window.postMessage({
          type: 'cup-response',
          id: requestId,
          result: { error: chrome.runtime.lastError.message },
          tier: 'error',
        }, '*');
        return;
      }
      // Forward response back to page
      window.postMessage({
        type: 'cup-response',
        ...response,
        id: requestId,
      }, '*');
    }
  );
});

// ── Extension → Page push (status updates) ──────────────────────────

chrome.runtime.onMessage.addListener((message) => {
  if (message.type === 'cup-status') {
    window.postMessage(message, '*');
  }
});

// ── Inject cupBridge API into page context ──────────────────────────

const apiScript = document.createElement('script');
apiScript.textContent = `
(function() {
  'use strict';

  // Pending response callbacks
  const _pending = new Map();
  let _statusCallback = null;
  let _detected = false;

  // Listen for responses from content script
  window.addEventListener('message', function(event) {
    if (event.source !== window) return;
    if (!event.data) return;

    if (event.data.type === 'cup-response') {
      const cb = _pending.get(event.data.id);
      if (cb) {
        _pending.delete(event.data.id);
        cb(event.data);
      }
    }

    if (event.data.type === 'cup-status' && _statusCallback) {
      _statusCallback(event.data);
    }
  });

  function _send(action, opts) {
    opts = opts || {};
    return new Promise(function(resolve, reject) {
      var id = 'cup-' + Date.now() + '-' + Math.random().toString(36).slice(2, 8);
      var timeout = opts.timeout || 30000;

      var timer = setTimeout(function() {
        _pending.delete(id);
        reject(new Error('CUP bridge timeout'));
      }, timeout);

      _pending.set(id, function(response) {
        clearTimeout(timer);
        resolve(response);
      });

      window.postMessage({
        type: 'cup-request',
        id: id,
        action: action,
        path: opts.path || '',
        body: opts.body || null,
        method: opts.method || 'GET',
        capability: opts.capability || '',
        preferTier: opts.preferTier || '',
      }, '*');
    });
  }

  /**
   * window.cupBridge — the public API exposed to the platform site.
   *
   * CUP Filter pattern: each method takes input, returns a Promise
   * of the result.  The extension pipeline handles routing.
   */
  window.cupBridge = {
    /** Check if extension is present. */
    get detected() { return true; },

    /** Ping the extension. */
    ping: function() { return _send('ping'); },

    /** Get full platform status. */
    status: function() { return _send('status'); },

    /** Delegate work to best available compute tier. */
    delegate: function(path, body, opts) {
      opts = opts || {};
      return _send('delegate', {
        path: path,
        body: body,
        method: opts.method || 'POST',
        preferTier: opts.preferTier || '',
      });
    },

    /** HTTP proxy through extension (bypasses CORS). */
    fetch: function(path, opts) {
      opts = opts || {};
      return _send('proxy', {
        path: path,
        body: opts.body || null,
        method: opts.method || 'GET',
      });
    },

    /** Provision a capability (download + install). */
    provision: function(recipe) {
      return _send('provision', { body: { recipe: recipe } });
    },

    /** Execute a command via native host. */
    exec: function(command, cwd) {
      return _send('exec', { body: { command: command, cwd: cwd || '' } });
    },

    /** Start spore_runner. */
    start: function(port, args) {
      return _send('start', { body: { port: port || 8089, args: args || [] } });
    },

    /** Stop spore_runner. */
    stop: function(pid) {
      return _send('stop', { body: { pid: pid } });
    },

    /** Get/set extension configuration. */
    getConfig: function() { return _send('get-config'); },
    setConfig: function(config) {
      return _send('set-config', { body: config });
    },

    /** Register a status change callback. */
    onStatus: function(callback) {
      _statusCallback = callback;
    },

    /** Trigger a manual probe/health check. */
    probe: function() { return _send('health'); },
  };

  // Signal to the page that cupBridge is ready
  window.dispatchEvent(new CustomEvent('cup-bridge-ready', {
    detail: { version: '1.0.0' }
  }));
})();
`;
(document.head || document.documentElement).appendChild(apiScript);
apiScript.remove();
