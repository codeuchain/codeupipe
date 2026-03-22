/**
 * cup-bridge-api.js — Injected into the MAIN world of the page.
 *
 * Defines window.cupBridge — the public API for page scripts to
 * communicate with the CUP extension via postMessage relay.
 *
 * This file runs in the page's JS context (not the isolated content
 * script world) so it can set window.cupBridge directly. It must be
 * registered with "world": "MAIN" in manifest.json.
 */
(function() {
  'use strict';

  // Pending response callbacks
  const _pending = new Map();
  let _statusCallback = null;

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
