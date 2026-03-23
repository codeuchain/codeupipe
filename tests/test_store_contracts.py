"""Tests for Capability Store, Service Worker, and Popup contracts.

Verifies that the platform store, service-worker pipeline, and extension
popup have correct structure, error handling, and tier routing logic.

Tests are structured in three tiers:
  1. Unit: static contract verification (read JS source, assert patterns)
  2. Integration: cross-file contract consistency
  3. Behaviour: verify provision flow logic, error messages, tier routing
"""

import json
import re
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_EXT_SRC = _PROJECT_ROOT / "codeupipe" / "connect" / "extension"
_PLATFORM_SRC = _EXT_SRC / "platform"


# ═══════════════════════════════════════════════════════════════════════
# TIER 1 — Unit: Store.js Contract
# ═══════════════════════════════════════════════════════════════════════


class TestStoreJsContract:
    """Verify store.js has the expected CUP Filter structure."""

    def test_has_load_manifest_filter(self):
        code = (_PLATFORM_SRC / "store.js").read_text()
        assert "function loadManifestFilter" in code

    def test_has_render_cards_filter(self):
        code = (_PLATFORM_SRC / "store.js").read_text()
        assert "function renderCardsFilter" in code

    def test_has_on_toggle_handler(self):
        code = (_PLATFORM_SRC / "store.js").read_text()
        assert "async function _onToggle" in code

    def test_has_extension_prompt(self):
        code = (_PLATFORM_SRC / "store.js").read_text()
        assert "function _showExtensionPrompt" in code

    def test_has_render_public_api(self):
        code = (_PLATFORM_SRC / "store.js").read_text()
        assert "async function render" in code
        assert "return { render }" in code

    def test_uses_cup_payload(self):
        code = (_PLATFORM_SRC / "store.js").read_text()
        assert "CupPlatform.Payload" in code

    def test_renders_not_installed_for_unchecked(self):
        """Initial render must show 'Not installed' for non-installed caps."""
        code = (_PLATFORM_SRC / "store.js").read_text()
        assert "'Not installed'" in code

    def test_renders_installed_for_checked(self):
        code = (_PLATFORM_SRC / "store.js").read_text()
        assert "'Installed'" in code

    def test_no_hardcoded_failed_in_render(self):
        """renderCardsFilter must NOT hardcode 'Failed' — only _onToggle may show it."""
        code = (_PLATFORM_SRC / "store.js").read_text()
        # Find the renderCardsFilter function body
        start = code.index("function renderCardsFilter")
        # Find the next top-level function
        end = code.index("async function _onToggle")
        render_body = code[start:end]
        assert "Failed" not in render_body, (
            "renderCardsFilter should not contain 'Failed' — "
            "that status should only appear in _onToggle error handling"
        )


class TestStoreErrorMessages:
    """Verify store shows actionable error messages, not generic 'Failed'."""

    def test_native_tier_shows_requires_native_host(self):
        """When provision fails for native-tier cap, show 'Requires native host'."""
        code = (_PLATFORM_SRC / "store.js").read_text()
        assert "'Requires native host'" in code

    def test_wasm_fallback_handled(self):
        """WASM fallback result should be handled gracefully."""
        code = (_PLATFORM_SRC / "store.js").read_text()
        assert "wasm-fallback" in code

    def test_wasm_tier_caps_show_available(self):
        """WASM-tier capabilities with wasm-fallback should show as available."""
        code = (_PLATFORM_SRC / "store.js").read_text()
        assert "'Available (WASM)" in code

    def test_on_toggle_checks_cap_tier(self):
        """_onToggle must check cap.tier to determine the right error message."""
        code = (_PLATFORM_SRC / "store.js").read_text()
        toggle_start = code.index("async function _onToggle")
        toggle_body = code[toggle_start:]
        assert "cap.tier" in toggle_body

    def test_no_bare_failed_string_in_toggle(self):
        """_onToggle should never show bare 'Failed' — must be tier-specific."""
        code = (_PLATFORM_SRC / "store.js").read_text()
        toggle_start = code.index("async function _onToggle")
        toggle_body = code[toggle_start:]
        # Should NOT contain statusEl.textContent = 'Failed' as a bare string
        assert "textContent = 'Failed'" not in toggle_body, (
            "Store should show tier-specific error, not bare 'Failed'"
        )


# ═══════════════════════════════════════════════════════════════════════
# TIER 1 — Unit: Service Worker Contract
# ═══════════════════════════════════════════════════════════════════════


class TestServiceWorkerContract:
    """Verify service-worker.js has CUP pipeline structure."""

    def test_has_payload_class(self):
        code = (_EXT_SRC / "service-worker.js").read_text()
        assert "class Payload" in code

    def test_has_parse_request_filter(self):
        code = (_EXT_SRC / "service-worker.js").read_text()
        assert "function parseRequest" in code

    def test_has_select_tier_filter(self):
        code = (_EXT_SRC / "service-worker.js").read_text()
        assert "function selectTier" in code

    def test_has_handle_internal_filter(self):
        code = (_EXT_SRC / "service-worker.js").read_text()
        assert "function handleInternal" in code

    def test_has_native_relay_filter(self):
        code = (_EXT_SRC / "service-worker.js").read_text()
        assert "async function nativeRelay" in code

    def test_has_http_proxy_filter(self):
        code = (_EXT_SRC / "service-worker.js").read_text()
        assert "async function httpProxy" in code

    def test_has_wasm_fallback_filter(self):
        code = (_EXT_SRC / "service-worker.js").read_text()
        assert "function wasmFallback" in code

    def test_has_format_response_filter(self):
        code = (_EXT_SRC / "service-worker.js").read_text()
        assert "function formatResponse" in code

    def test_has_run_pipeline(self):
        code = (_EXT_SRC / "service-worker.js").read_text()
        assert "async function runPipeline" in code

    def test_pipeline_order(self):
        """Pipeline must run filters in correct order."""
        code = (_EXT_SRC / "service-worker.js").read_text()
        pipeline_start = code.index("async function runPipeline")
        pipeline_body = code[pipeline_start:pipeline_start + 500]
        # Each filter must appear in order
        order = ["parseRequest", "selectTier", "handleInternal",
                 "nativeRelay", "httpProxy", "wasmFallback", "formatResponse"]
        positions = []
        for fn in order:
            pos = pipeline_body.find(fn)
            assert pos >= 0, f"Pipeline missing {fn}"
            positions.append(pos)
        assert positions == sorted(positions), "Pipeline filters out of order"


class TestServiceWorkerTierRouting:
    """Verify SelectTierFilter routes provision correctly."""

    def test_provision_not_hardcoded_to_native(self):
        """selectTier must NOT unconditionally route provision to native."""
        code = (_EXT_SRC / "service-worker.js").read_text()
        tier_start = code.index("function selectTier")
        # Find end of selectTier (next top-level function)
        tier_end = code.index("function handleInternal")
        tier_body = code[tier_start:tier_end]

        # Must NOT have the old pattern: if provision → return native
        # Pattern: single-line 'provision'...return...insert('tier', 'native')
        # with no conditional check around it
        lines = tier_body.split("\n")
        for i, line in enumerate(lines):
            if "'provision'" in line and "return" in line and "'native'" in line:
                # This is the old hardcoded pattern
                pytest.fail(
                    f"selectTier still hardcodes provision→native at line: {line.strip()}"
                )

    def test_provision_respects_prefer_tier(self):
        """selectTier should check preferTier for provision actions."""
        code = (_EXT_SRC / "service-worker.js").read_text()
        tier_start = code.index("function selectTier")
        tier_end = code.index("function handleInternal")
        tier_body = code[tier_start:tier_end]
        # Must have prefer_tier checks within the provision block
        assert "preferTier" in tier_body
        assert "'provision'" in tier_body

    def test_provision_auto_selects_best_available(self):
        """When no preferTier, provision should auto-select best available tier."""
        code = (_EXT_SRC / "service-worker.js").read_text()
        tier_start = code.index("function selectTier")
        tier_end = code.index("function handleInternal")
        tier_body = code[tier_start:tier_end]
        # Must have fallback cascade: native → http → wasm
        assert "state.nativeAlive" in tier_body
        assert "state.httpAlive" in tier_body
        assert "'wasm'" in tier_body

    def test_internal_actions_routed_to_internal(self):
        """ping, status, get-config, set-config → 'internal'."""
        code = (_EXT_SRC / "service-worker.js").read_text()
        tier_start = code.index("function selectTier")
        tier_end = code.index("function handleInternal")
        tier_body = code[tier_start:tier_end]
        for action in ["ping", "status", "get-config", "set-config"]:
            assert f"'{action}'" in tier_body


class TestNativeRelayFallthrough:
    """Verify nativeRelay falls through to HTTP/WASM on failure."""

    def test_native_relay_sets_native_error_on_failure(self):
        code = (_EXT_SRC / "service-worker.js").read_text()
        relay_start = code.index("async function nativeRelay")
        relay_end = code.index("async function httpProxy")
        relay_body = code[relay_start:relay_end]
        assert "'native_error'" in relay_body

    def test_native_relay_does_not_hardcode_response_on_failure(self):
        """On NM failure, nativeRelay must NOT set response directly —
        it must fall through to httpProxy/wasmFallback."""
        code = (_EXT_SRC / "service-worker.js").read_text()
        relay_start = code.index("async function nativeRelay")
        relay_end = code.index("async function httpProxy")
        relay_body = code[relay_start:relay_end]
        # The catch block should NOT contain insert('response', ...)
        catch_start = relay_body.index("} catch")
        catch_body = relay_body[catch_start:]
        assert "insert('response'" not in catch_body, (
            "nativeRelay catch block should not set response — "
            "must fall through to next filter"
        )

    def test_native_relay_falls_through_to_http_or_wasm(self):
        code = (_EXT_SRC / "service-worker.js").read_text()
        relay_start = code.index("async function nativeRelay")
        relay_end = code.index("async function httpProxy")
        relay_body = code[relay_start:relay_end]
        catch_start = relay_body.index("} catch")
        catch_body = relay_body[catch_start:]
        # Must update tier to http or wasm
        assert "insert('tier'" in catch_body


# ═══════════════════════════════════════════════════════════════════════
# TIER 1 — Unit: Popup Contract
# ═══════════════════════════════════════════════════════════════════════


class TestPopupContract:
    """Verify popup.html has correct structure and URLs."""

    def test_popup_exists(self):
        assert (_EXT_SRC / "popup.html").is_file()

    def test_popup_has_platform_button(self):
        code = (_EXT_SRC / "popup.html").read_text()
        assert "btn-platform" in code

    def test_popup_has_probe_button(self):
        code = (_EXT_SRC / "popup.html").read_text()
        assert "btn-probe" in code

    def test_popup_platform_url_correct(self):
        """Platform button must link to the correct GitHub Pages URL."""
        code = (_EXT_SRC / "popup.html").read_text()
        assert "codeuchain.github.io/codeupipe/platform/" in code

    def test_popup_platform_url_not_old(self):
        """Must not use the old cup-platform URL."""
        code = (_EXT_SRC / "popup.html").read_text()
        assert "cup-platform" not in code, (
            "Popup still uses old cup-platform URL"
        )

    def test_popup_sends_cup_request(self):
        code = (_EXT_SRC / "popup.html").read_text()
        assert "cup-request" in code
        assert "chrome.runtime.sendMessage" in code

    def test_popup_has_tier_display(self):
        code = (_EXT_SRC / "popup.html").read_text()
        assert "TIER_DISPLAY" in code
        assert "tier-native" in code
        assert "tier-wasm" in code


# ═══════════════════════════════════════════════════════════════════════
# TIER 1 — Unit: Cup Bridge API Contract (provision)
# ═══════════════════════════════════════════════════════════════════════


class TestCupBridgeApiProvision:
    """Verify cup-bridge-api.js provision sends preferTier."""

    def test_provision_accepts_prefer_tier(self):
        """provision(recipe, preferTier) must forward preferTier to _send."""
        code = (_EXT_SRC / "cup-bridge-api.js").read_text()
        # Find the provision method
        prov_match = re.search(r'provision:\s*function\s*\(([^)]*)\)', code)
        assert prov_match, "provision method not found"
        params = prov_match.group(1)
        assert "preferTier" in params, (
            f"provision should accept preferTier param, got: ({params})"
        )

    def test_provision_passes_prefer_tier_to_send(self):
        code = (_EXT_SRC / "cup-bridge-api.js").read_text()
        prov_start = code.index("provision: function")
        # Get the provision function body (up to next method)
        prov_body = code[prov_start:prov_start + 300]
        assert "preferTier" in prov_body


# ═══════════════════════════════════════════════════════════════════════
# TIER 1 — Unit: Platform.js Provision Contract
# ═══════════════════════════════════════════════════════════════════════


class TestPlatformJsProvision:
    """Verify platform.js passes recipe tier to cupBridge.provision."""

    def test_provision_passes_recipe_tier(self):
        code = (_PLATFORM_SRC / "platform.js").read_text()
        # Should pass recipe.tier to cupBridge.provision
        assert "cupBridge.provision(recipe, recipe.tier)" in code

    def test_provision_loads_recipe_json(self):
        code = (_PLATFORM_SRC / "platform.js").read_text()
        assert "recipes/${recipeId}.json" in code


# ═══════════════════════════════════════════════════════════════════════
# TIER 2 — Integration: Cross-file consistency
# ═══════════════════════════════════════════════════════════════════════


class TestCrossFileConsistency:
    """Verify platform.js, store.js, service-worker.js, and cup-bridge-api.js
    are consistent with each other."""

    def test_store_uses_cup_platform_provision(self):
        """Store must call CupPlatform.provision for toggle handling."""
        code = (_PLATFORM_SRC / "store.js").read_text()
        assert "CupPlatform.provision" in code

    def test_platform_provision_uses_cup_bridge(self):
        """Platform must call cupBridge.provision."""
        code = (_PLATFORM_SRC / "platform.js").read_text()
        assert "window.cupBridge.provision" in code

    def test_cup_bridge_provision_sends_cup_request(self):
        """cupBridge.provision must use _send which sends cup-request."""
        code = (_EXT_SRC / "cup-bridge-api.js").read_text()
        # provision calls _send
        assert "_send('provision'" in code

    def test_service_worker_handles_provision_action(self):
        """Service worker selectTier must handle 'provision' action."""
        code = (_EXT_SRC / "service-worker.js").read_text()
        assert "'provision'" in code

    def test_recipe_manifest_tiers_match_valid_values(self):
        """All recipe tiers must be 'native', 'http', or 'wasm'."""
        manifest = json.loads(
            (_EXT_SRC / "recipes" / "manifest.json").read_text()
        )
        valid_tiers = {"native", "http", "wasm"}
        for cap in manifest["capabilities"]:
            assert cap["tier"] in valid_tiers, (
                f"Recipe {cap['id']} has invalid tier: {cap['tier']}"
            )

    def test_store_tier_badge_covers_all_recipe_tiers(self):
        """Store's _tierBadge helper must cover all tier values in recipes."""
        store_code = (_PLATFORM_SRC / "store.js").read_text()
        manifest = json.loads(
            (_EXT_SRC / "recipes" / "manifest.json").read_text()
        )
        tiers_used = {cap["tier"] for cap in manifest["capabilities"]}
        for tier in tiers_used:
            assert tier in store_code, f"Store missing tier badge for: {tier}"

    def test_popup_and_platform_share_github_org(self):
        """Popup and platform index.html must reference the same GitHub org."""
        popup_code = (_EXT_SRC / "popup.html").read_text()
        index_code = (_PLATFORM_SRC / "index.html").read_text()
        assert "codeuchain" in popup_code
        assert "codeuchain" in index_code


# ═══════════════════════════════════════════════════════════════════════
# TIER 3 — Behaviour: WasmFallback filter
# ═══════════════════════════════════════════════════════════════════════


class TestWasmFallbackBehaviour:
    """Verify the wasmFallback filter produces correct response structure."""

    def test_wasm_fallback_sets_status(self):
        code = (_EXT_SRC / "service-worker.js").read_text()
        fb_start = code.index("function wasmFallback")
        fb_end = code.index("function formatResponse")
        fb_body = code[fb_start:fb_end]
        assert "'wasm-fallback'" in fb_body

    def test_wasm_fallback_sets_tier_wasm(self):
        code = (_EXT_SRC / "service-worker.js").read_text()
        fb_start = code.index("function wasmFallback")
        fb_end = code.index("function formatResponse")
        fb_body = code[fb_start:fb_end]
        assert "'wasm'" in fb_body

    def test_wasm_fallback_skips_if_response_exists(self):
        """wasmFallback must skip if response already set by prior filter."""
        code = (_EXT_SRC / "service-worker.js").read_text()
        fb_start = code.index("function wasmFallback")
        fb_end = code.index("function formatResponse")
        fb_body = code[fb_start:fb_end]
        assert "get('response')" in fb_body


# ═══════════════════════════════════════════════════════════════════════
# TIER 3 — Behaviour: broadcastStatus safety
# ═══════════════════════════════════════════════════════════════════════


class TestBroadcastStatusContract:
    """Verify broadcastStatus only targets tabs with content scripts
    and consumes chrome.runtime.lastError to prevent unhandled errors."""

    def test_queries_with_url_filter(self):
        """broadcastStatus must pass { url: [...] } to chrome.tabs.query,
        NOT an empty filter that hits every tab."""
        code = (_EXT_SRC / "service-worker.js").read_text()
        bc_start = code.index("function broadcastStatus")
        # broadcastStatus ends at the next top-level section
        bc_end = code.index("// ── Message Listeners")
        bc_body = code[bc_start:bc_end]
        assert "chrome.tabs.query({ url:" in bc_body or \
               "chrome.tabs.query({url:" in bc_body, (
            "broadcastStatus must filter tabs by URL pattern, "
            "not query all tabs with {}"
        )

    def test_does_not_query_all_tabs(self):
        """Must NOT call chrome.tabs.query({}, ...) which hits every tab."""
        code = (_EXT_SRC / "service-worker.js").read_text()
        bc_start = code.index("function broadcastStatus")
        bc_end = code.index("// ── Message Listeners")
        bc_body = code[bc_start:bc_end]
        # The old pattern: chrome.tabs.query({}, (tabs) => {
        assert "chrome.tabs.query({}, " not in bc_body, (
            "broadcastStatus still queries ALL tabs — "
            "must filter by content script URL patterns"
        )

    def test_url_patterns_match_content_script_manifest(self):
        """URL patterns in broadcastStatus must include all content_scripts
        match patterns from manifest.json."""
        sw_code = (_EXT_SRC / "service-worker.js").read_text()
        manifest = json.loads((_EXT_SRC / "manifest.json").read_text())

        bc_start = sw_code.index("function broadcastStatus")
        bc_end = sw_code.index("// ── Message Listeners")
        bc_body = sw_code[bc_start:bc_end]

        # Collect unique match patterns from manifest
        manifest_patterns = set()
        for entry in manifest.get("content_scripts", []):
            for pattern in entry.get("matches", []):
                manifest_patterns.add(pattern)

        for pattern in manifest_patterns:
            assert pattern in bc_body, (
                f"broadcastStatus missing URL pattern from manifest: {pattern}"
            )

    def test_consumes_last_error_in_send_callback(self):
        """chrome.tabs.sendMessage must have a callback that reads
        chrome.runtime.lastError to suppress the unhandled error."""
        code = (_EXT_SRC / "service-worker.js").read_text()
        bc_start = code.index("function broadcastStatus")
        bc_end = code.index("// ── Message Listeners")
        bc_body = code[bc_start:bc_end]
        # Must use the callback form of sendMessage
        assert "chrome.tabs.sendMessage(tab.id, statusMsg," in bc_body or \
               "sendMessage(tab.id, statusMsg, " in bc_body, (
            "broadcastStatus must use callback form of sendMessage"
        )
        # Must consume lastError
        assert "chrome.runtime.lastError" in bc_body, (
            "broadcastStatus callback must read chrome.runtime.lastError"
        )

    def test_no_bare_try_catch_around_send(self):
        """try/catch doesn't help for async Chrome API errors —
        the callback + lastError pattern is required."""
        code = (_EXT_SRC / "service-worker.js").read_text()
        bc_start = code.index("function broadcastStatus")
        bc_end = code.index("// ── Message Listeners")
        bc_body = code[bc_start:bc_end]
        # Should NOT have try { sendMessage } catch pattern
        assert "try {" not in bc_body, (
            "broadcastStatus should use callback form, not try/catch"
        )
