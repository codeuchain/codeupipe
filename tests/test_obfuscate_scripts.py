"""Tests for ObfuscateScripts — JavaScript obfuscation via subprocess."""

from unittest.mock import patch

from codeupipe import Payload
from codeupipe.deploy.obfuscate.obfuscate_scripts import ObfuscateScripts


class TestObfuscateScripts:
    def _make_payload(self, blocks=None):
        return Payload({
            "script_blocks": blocks or [],
            "config": {
                "js_opts": {"compact": True},
                "reserved_names": [],
                "reserved_strings": [],
            },
        })

    @patch("codeupipe.deploy.obfuscate.transform_code._find_obfuscator")
    def test_no_tool_passthrough(self, mock_find):
        """When javascript-obfuscator is not installed, pass through original code."""
        mock_find.return_value = ""
        blocks = [{"code": "alert(1)", "placeholder": "PH_0"}]

        f = ObfuscateScripts(strict=False)
        result = f.call(self._make_payload(blocks))

        obfuscated = result.get("obfuscated_blocks")
        assert len(obfuscated) == 1
        assert obfuscated[0]["obfuscated_code"] == "alert(1)"

        stats = result.get("obfuscate_stats")
        assert stats["skipped"] == 1
        assert stats["obfuscated"] == 0

    @patch("codeupipe.deploy.obfuscate.transform_code._find_obfuscator")
    def test_strict_mode_raises(self, mock_find):
        """When strict=True and no tool, raise RuntimeError."""
        mock_find.return_value = ""
        import pytest
        f = ObfuscateScripts(strict=True)
        with pytest.raises(RuntimeError, match="javascript-obfuscator not found"):
            f.call(self._make_payload([{"code": "x", "placeholder": "PH"}]))

    @patch("codeupipe.deploy.obfuscate.transform_code._find_obfuscator")
    @patch("codeupipe.deploy.obfuscate.transform_code._obfuscate_one")
    def test_successful_obfuscation(self, mock_obf, mock_find):
        """When tool is available, obfuscate code."""
        mock_find.return_value = "/usr/bin/javascript-obfuscator"
        mock_obf.return_value = "var _0x1234=function(){}"

        blocks = [{"code": "function hello() {}", "placeholder": "PH_0"}]
        f = ObfuscateScripts()
        result = f.call(self._make_payload(blocks))

        obfuscated = result.get("obfuscated_blocks")
        assert obfuscated[0]["obfuscated_code"] == "var _0x1234=function(){}"
        assert result.get("obfuscate_stats")["obfuscated"] == 1

    @patch("codeupipe.deploy.obfuscate.transform_code._find_obfuscator")
    @patch("codeupipe.deploy.obfuscate.transform_code._obfuscate_one")
    def test_error_fallback(self, mock_obf, mock_find):
        """When obfuscation fails, fall back to original code."""
        mock_find.return_value = "/usr/bin/javascript-obfuscator"
        mock_obf.side_effect = RuntimeError("obfuscator crashed")

        blocks = [{"code": "original()", "placeholder": "PH_0"}]
        f = ObfuscateScripts()
        result = f.call(self._make_payload(blocks))

        obfuscated = result.get("obfuscated_blocks")
        assert obfuscated[0]["obfuscated_code"] == "original()"
        assert result.get("obfuscate_stats")["errors"] == 1

    def test_empty_blocks(self):
        f = ObfuscateScripts()
        result = f.call(self._make_payload([]))
        assert result.get("obfuscated_blocks") == []
        assert result.get("obfuscate_stats")["total"] == 0
