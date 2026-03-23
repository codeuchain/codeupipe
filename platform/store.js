/**
 * store.js — Capability Store component.
 *
 * CUP/TS pattern: Each store action is a Filter that transforms a Payload.
 * The store renders recipes from the manifest and handles provisioning.
 */

const CupStore = (function () {
  'use strict';

  const Payload = CupPlatform.Payload;

  // ── CUP Filters ────────────────────────────────────────────────

  function loadManifestFilter(payload) {
    const recipes = CupPlatform.recipes;
    if (!recipes) return payload.insert('error', 'No recipes loaded');
    return payload.insert('capabilities', recipes.capabilities);
  }

  function renderCardsFilter(payload) {
    const capabilities = payload.get('capabilities', []);
    const container = payload.get('container');
    if (!container) return payload.insert('error', 'No container element');

    container.innerHTML = '';

    for (const cap of capabilities) {
      const card = document.createElement('div');
      card.className = 'cup-store-card';
      card.dataset.id = cap.id;

      const installed = CupPlatform.installed.includes(cap.id);
      const tierBadge = _tierBadge(cap.tier);

      card.innerHTML = `
        <div class="cup-store-card-header">
          <span class="cup-store-icon">${cap.icon || '📦'}</span>
          <span class="cup-store-tier">${tierBadge}</span>
        </div>
        <h3 class="cup-store-name">${_esc(cap.name)}</h3>
        <p class="cup-store-desc">${_esc(cap.description)}</p>
        <div class="cup-store-actions">
          <label class="cup-store-toggle">
            <input type="checkbox" ${installed ? 'checked' : ''}
                   data-recipe="${_esc(cap.id)}" />
            <span class="cup-store-slider"></span>
          </label>
          <span class="cup-store-status">${installed ? 'Installed' : 'Not installed'}</span>
        </div>
        <div class="cup-store-progress" style="display:none">
          <div class="cup-store-progress-bar"></div>
          <span class="cup-store-progress-text"></span>
        </div>
      `;

      // Toggle handler
      const toggle = card.querySelector('input[type="checkbox"]');
      toggle.addEventListener('change', (e) => _onToggle(e, card, cap));

      container.appendChild(card);
    }

    return payload.insert('rendered', capabilities.length);
  }

  // ── Toggle Handler (provision pipeline) ────────────────────────

  async function _onToggle(event, card, cap) {
    const checked = event.target.checked;
    const statusEl = card.querySelector('.cup-store-status');
    const progressEl = card.querySelector('.cup-store-progress');
    const progressBar = card.querySelector('.cup-store-progress-bar');
    const progressText = card.querySelector('.cup-store-progress-text');

    if (!checked) {
      statusEl.textContent = 'Not installed';
      card.classList.remove('installed');
      return;
    }

    if (!CupPlatform.detected) {
      statusEl.textContent = 'Extension required';
      event.target.checked = false;
      _showExtensionPrompt();
      return;
    }

    // Show progress
    progressEl.style.display = 'block';
    progressBar.style.width = '0%';
    progressText.textContent = 'Starting…';
    statusEl.textContent = 'Installing…';
    card.classList.add('installing');

    try {
      const result = await CupPlatform.provision(cap.id, (progress) => {
        if (progress.phase === 'start') {
          progressBar.style.width = '30%';
          progressText.textContent = 'Provisioning…';
        } else if (progress.phase === 'complete') {
          progressBar.style.width = '100%';
          progressText.textContent = 'Done';
        }
      });

      if (result.result && result.result.success) {
        statusEl.textContent = 'Installed ✓';
        card.classList.remove('installing');
        card.classList.add('installed');
      } else if (result.result && result.result.status === 'wasm-fallback') {
        // WASM fallback — capability is available in-browser
        if (cap.tier === 'wasm') {
          statusEl.textContent = 'Available (WASM) ✓';
          card.classList.remove('installing');
          card.classList.add('installed');
        } else {
          statusEl.textContent = 'Requires native host';
          event.target.checked = false;
          card.classList.remove('installing');
        }
      } else {
        // Provide actionable error based on capability tier
        statusEl.textContent = cap.tier === 'native'
          ? 'Requires native host'
          : 'Provision failed';
        event.target.checked = false;
        card.classList.remove('installing');
      }
    } catch (err) {
      statusEl.textContent = `Error: ${err.message}`;
      event.target.checked = false;
      card.classList.remove('installing');
    }

    // Fade out progress after 2s
    setTimeout(() => { progressEl.style.display = 'none'; }, 2000);
  }

  // ── Extension Prompt ───────────────────────────────────────────

  function _showExtensionPrompt() {
    const existing = document.getElementById('cup-ext-prompt');
    if (existing) { existing.style.display = 'flex'; return; }

    const overlay = document.createElement('div');
    overlay.id = 'cup-ext-prompt';
    overlay.className = 'cup-overlay';
    overlay.innerHTML = `
      <div class="cup-modal">
        <h2>CUP Bridge Extension Required</h2>
        <p>To provision capabilities on your device, install the CUP Platform Bridge extension.</p>

        <h4 style="margin-top:1rem;">🖥️ Desktop (Chrome / Edge / Brave)</h4>
        <ol>
          <li>Download <code>cup-bridge-extension.zip</code></li>
          <li>Open <code>chrome://extensions</code></li>
          <li>Enable "Developer mode"</li>
          <li>Click "Load unpacked" and select the extracted folder</li>
        </ol>

        <h4 style="margin-top:1rem;">📱 Android (Edge Canary)</h4>
        <ol>
          <li>Download <code>cup-bridge-android.crx</code></li>
          <li>Settings → About Edge → tap build number 7×</li>
          <li>Developer Options → "Extension install by crx"</li>
          <li>Select the <code>.crx</code> file → tap Add</li>
        </ol>

        <div class="cup-modal-actions">
          <a href="cup-bridge-extension.zip" class="cup-btn cup-btn-primary" download>
            ⬇️ Desktop ZIP
          </a>
          <a href="cup-bridge-android.crx" class="cup-btn cup-btn-primary" download>
            📱 Android CRX
          </a>
          <button class="cup-btn cup-btn-secondary" onclick="this.closest('.cup-overlay').style.display='none'">
            Close
          </button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);
  }

  // ── Helpers ────────────────────────────────────────────────────

  function _esc(s) {
    const el = document.createElement('span');
    el.textContent = s;
    return el.innerHTML;
  }

  function _tierBadge(tier) {
    const badges = {
      native: '<span class="tier-badge tier-native">Native</span>',
      http: '<span class="tier-badge tier-http">HTTP</span>',
      wasm: '<span class="tier-badge tier-wasm">WASM</span>',
    };
    return badges[tier] || `<span class="tier-badge">${tier}</span>`;
  }

  // ── Public: run the store pipeline ────────────────────────────

  async function render(containerSelector) {
    const container = document.querySelector(containerSelector);
    let payload = new Payload({ container });

    // CUP Pipeline: load → render
    payload = loadManifestFilter(payload);
    payload = renderCardsFilter(payload);

    return payload;
  }

  return { render };
})();
