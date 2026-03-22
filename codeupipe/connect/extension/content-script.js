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

// ── NOTE: window.cupBridge API is now injected by cup-bridge-api.js ──
// Registered in manifest.json with "world": "MAIN" to bypass CSP.
// The old inline <script> injection was blocked by GitHub Pages CSP.

// ── Extension-owned status injection ────────────────────────────────
// The extension renders its own status into the page DOM so the site
// does not need to detect the extension — the extension announces itself.

function injectExtensionStatus() {
  // Only inject on CUP platform pages
  const isCupSite = location.hostname === 'codeuchain.github.io'
    || location.hostname === 'localhost'
    || location.hostname === '127.0.0.1';
  if (!isCupSite) return;

  // Wait for DOM to be ready
  function doInject() {
    // Don't double-inject
    if (document.getElementById('cup-ext-status')) return;

    // Create the status badge
    const badge = document.createElement('div');
    badge.id = 'cup-ext-status';
    badge.innerHTML = `
      <style>
        #cup-ext-status {
          position: fixed;
          bottom: 16px;
          right: 16px;
          z-index: 99999;
          background: #1e1e2e;
          border: 1px solid #7c4dff;
          border-radius: 10px;
          padding: 12px 16px;
          color: #cdd6f4;
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
          font-size: 13px;
          box-shadow: 0 4px 20px rgba(124, 77, 255, 0.3);
          min-width: 220px;
          transition: opacity 0.3s;
        }
        #cup-ext-status .cup-badge-title {
          font-weight: 600;
          margin-bottom: 6px;
          color: #7c4dff;
          font-size: 14px;
        }
        #cup-ext-status .cup-badge-row {
          display: flex;
          justify-content: space-between;
          margin: 3px 0;
        }
        #cup-ext-status .cup-badge-label { color: #a6adc8; }
        #cup-ext-status .cup-badge-value { font-weight: 500; }
        #cup-ext-status .cup-badge-ok { color: #a6e3a1; }
        #cup-ext-status .cup-badge-warn { color: #f9e2af; }
        #cup-ext-status .cup-badge-err { color: #f38ba8; }
        #cup-ext-status .cup-badge-close {
          position: absolute; top: 6px; right: 10px;
          cursor: pointer; color: #6c7086; font-size: 16px;
          background: none; border: none; padding: 0;
        }
        #cup-ext-status .cup-badge-close:hover { color: #cdd6f4; }
      </style>
      <button class="cup-badge-close" title="Dismiss">&times;</button>
      <div class="cup-badge-title">🔌 CUP Bridge Extension</div>
      <div class="cup-badge-row">
        <span class="cup-badge-label">Extension</span>
        <span class="cup-badge-value cup-badge-ok">✅ Active</span>
      </div>
      <div class="cup-badge-row">
        <span class="cup-badge-label">Tier</span>
        <span class="cup-badge-value" id="cup-ext-tier">⏳ Probing…</span>
      </div>
      <div class="cup-badge-row">
        <span class="cup-badge-label">Native Host</span>
        <span class="cup-badge-value" id="cup-ext-native">⏳ …</span>
      </div>
      <div class="cup-badge-row">
        <span class="cup-badge-label">HTTP Server</span>
        <span class="cup-badge-value" id="cup-ext-http">⏳ …</span>
      </div>
    `;
    document.body.appendChild(badge);

    // Dismiss button
    badge.querySelector('.cup-badge-close').addEventListener('click', () => {
      badge.style.opacity = '0';
      setTimeout(() => badge.remove(), 300);
    });

    // Probe the service worker for status
    chrome.runtime.sendMessage(
      { type: 'cup-request', action: 'status', id: 'badge-probe-' + Date.now() },
      (response) => {
        const tierEl = document.getElementById('cup-ext-tier');
        const nativeEl = document.getElementById('cup-ext-native');
        const httpEl = document.getElementById('cup-ext-http');

        if (chrome.runtime.lastError || !response || !response.result) {
          if (tierEl) tierEl.innerHTML = '<span class="cup-badge-warn">🟡 WASM fallback</span>';
          if (nativeEl) nativeEl.innerHTML = '<span class="cup-badge-err">❌ Unreachable</span>';
          if (httpEl) httpEl.innerHTML = '<span class="cup-badge-err">❌ Unreachable</span>';
          return;
        }

        const r = response.result;
        const tier = r.tier || 'unknown';
        const tierLabels = {
          'extension-native': '<span class="cup-badge-ok">🟢 Native</span>',
          'extension-http': '<span class="cup-badge-ok">🔵 HTTP</span>',
          'extension-wasm': '<span class="cup-badge-warn">🟡 WASM</span>',
          'wasm': '<span class="cup-badge-warn">🟡 WASM</span>',
          'disconnected': '<span class="cup-badge-err">🔴 Disconnected</span>',
        };
        if (tierEl) tierEl.innerHTML = tierLabels[tier] || `<span class="cup-badge-warn">❓ ${tier}</span>`;
        if (nativeEl) nativeEl.innerHTML = r.nativeAlive
          ? '<span class="cup-badge-ok">✅ Connected</span>'
          : '<span class="cup-badge-err">❌ Not running</span>';
        if (httpEl) httpEl.innerHTML = r.httpAlive
          ? '<span class="cup-badge-ok">✅ Connected</span>'
          : '<span class="cup-badge-err">❌ Not running</span>';
      }
    );
  }

  if (document.body) {
    doInject();
  } else {
    document.addEventListener('DOMContentLoaded', doInject);
  }
}

injectExtensionStatus();