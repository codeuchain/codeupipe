"""
Unit tests for codeupipe-resend connector.

All tests mock the resend SDK via sys.modules — no pip install needed.
"""

import asyncio
import sys
from unittest.mock import MagicMock

import pytest

from codeupipe import Payload


# ── Module-level mocks for resend ───────────────────────────────────

_mock_resend = MagicMock()
_mock_resend.__name__ = "resend"
_mock_resend.__spec__ = None


@pytest.fixture(autouse=True)
def mock_resend_module():
    """Inject mock resend into sys.modules for all tests."""
    original = sys.modules.get("resend")
    sys.modules["resend"] = _mock_resend
    _mock_resend.reset_mock()
    yield
    if original is None:
        sys.modules.pop("resend", None)
    else:
        sys.modules["resend"] = original
    for key in list(sys.modules):
        if key.startswith("codeupipe_resend"):
            del sys.modules[key]


# ── ResendEmail ─────────────────────────────────────────────────────


class TestResendEmail:
    def test_send_html_email(self):
        from codeupipe_resend.email import ResendEmail

        _mock_resend.Emails.send.return_value = {"id": "email_123"}

        f = ResendEmail(api_key="re_test_fake", default_from="noreply@example.com")
        payload = Payload({
            "to": "user@example.com",
            "subject": "Hello",
            "html": "<h1>Hi</h1>",
        })
        result = asyncio.get_event_loop().run_until_complete(f.call(payload))

        assert result.get("email_id") == "email_123"
        call_args = _mock_resend.Emails.send.call_args[0][0]
        assert call_args["to"] == ["user@example.com"]
        assert call_args["subject"] == "Hello"
        assert call_args["html"] == "<h1>Hi</h1>"

    def test_send_text_email(self):
        from codeupipe_resend.email import ResendEmail

        _mock_resend.Emails.send.return_value = {"id": "email_456"}

        f = ResendEmail(api_key="re_test_fake", default_from="noreply@example.com")
        payload = Payload({
            "to": ["a@x.com", "b@x.com"],
            "subject": "Plain",
            "text": "Hello plain",
        })
        result = asyncio.get_event_loop().run_until_complete(f.call(payload))

        assert result.get("email_id") == "email_456"
        call_args = _mock_resend.Emails.send.call_args[0][0]
        assert call_args["text"] == "Hello plain"
        assert "html" not in call_args

    def test_from_address_override(self):
        from codeupipe_resend.email import ResendEmail

        _mock_resend.Emails.send.return_value = {"id": "email_789"}

        f = ResendEmail(api_key="re_test_fake", default_from="default@x.com")
        payload = Payload({
            "to": "u@x.com",
            "subject": "Test",
            "html": "<p>hi</p>",
            "from_address": "custom@x.com",
        })
        asyncio.get_event_loop().run_until_complete(f.call(payload))

        call_args = _mock_resend.Emails.send.call_args[0][0]
        assert call_args["from_"] == "custom@x.com"

    def test_string_to_becomes_list(self):
        from codeupipe_resend.email import ResendEmail

        _mock_resend.Emails.send.return_value = {"id": "email_list"}

        f = ResendEmail(api_key="re_test_fake", default_from="noreply@x.com")
        payload = Payload({"to": "single@x.com", "subject": "Test", "html": "<p>hi</p>"})
        asyncio.get_event_loop().run_until_complete(f.call(payload))

        call_args = _mock_resend.Emails.send.call_args[0][0]
        assert call_args["to"] == ["single@x.com"]


# ── ResendTemplate ──────────────────────────────────────────────────


class TestResendTemplate:
    def test_template_variable_replacement(self):
        from codeupipe_resend.template import ResendTemplate

        _mock_resend.Emails.send.return_value = {"id": "tmpl_001"}

        f = ResendTemplate(api_key="re_test_fake", default_from="noreply@x.com")
        payload = Payload({
            "to": "user@x.com",
            "subject": "Welcome",
            "html": "<h1>Hello {{name}}</h1><p>Order: {{order_id}}</p>",
            "variables": {"name": "Alice", "order_id": "ORD-123"},
        })
        result = asyncio.get_event_loop().run_until_complete(f.call(payload))

        assert result.get("email_id") == "tmpl_001"
        call_args = _mock_resend.Emails.send.call_args[0][0]
        assert "Alice" in call_args["html"]
        assert "ORD-123" in call_args["html"]
        assert "{{name}}" not in call_args["html"]

    def test_empty_variables(self):
        from codeupipe_resend.template import ResendTemplate

        _mock_resend.Emails.send.return_value = {"id": "tmpl_002"}

        f = ResendTemplate(api_key="re_test_fake", default_from="noreply@x.com")
        payload = Payload({
            "to": "user@x.com",
            "subject": "No vars",
            "html": "<p>Static content</p>",
        })
        result = asyncio.get_event_loop().run_until_complete(f.call(payload))

        assert result.get("email_id") == "tmpl_002"
