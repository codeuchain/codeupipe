"""
Unit tests for codeupipe-stripe connector.

All tests mock the stripe SDK via sys.modules — no pip install needed.
"""

import asyncio
import sys
from types import SimpleNamespace, ModuleType
from unittest.mock import MagicMock

import pytest

from codeupipe import Payload


# ── Module-level mocks for stripe ───────────────────────────────────

_mock_stripe = MagicMock()
_mock_stripe.__name__ = "stripe"
_mock_stripe.__spec__ = None


@pytest.fixture(autouse=True)
def mock_stripe_module():
    """Inject mock stripe into sys.modules for all tests."""
    original = sys.modules.get("stripe")
    sys.modules["stripe"] = _mock_stripe
    _mock_stripe.reset_mock()
    yield
    if original is None:
        sys.modules.pop("stripe", None)
    else:
        sys.modules["stripe"] = original
    for key in list(sys.modules):
        if key.startswith("codeupipe_stripe"):
            del sys.modules[key]


# ── StripeCheckout ──────────────────────────────────────────────────


class TestStripeCheckout:
    def test_creates_checkout_session(self):
        from codeupipe_stripe.checkout import StripeCheckout

        mock_session = SimpleNamespace(url="https://checkout.stripe.com/xyz", id="cs_123")
        _mock_stripe.checkout.Session.create.return_value = mock_session

        f = StripeCheckout(api_key="sk_test_fake")
        payload = Payload({
            "line_items": [{"price": "price_123", "quantity": 1}],
            "success_url": "https://example.com/success",
            "cancel_url": "https://example.com/cancel",
        })
        result = asyncio.get_event_loop().run_until_complete(f.call(payload))

        assert result.get("checkout_url") == "https://checkout.stripe.com/xyz"
        assert result.get("session_id") == "cs_123"

    def test_passes_idempotency_key(self):
        from codeupipe_stripe.checkout import StripeCheckout

        mock_session = SimpleNamespace(url="https://stripe.com", id="cs_456")
        _mock_stripe.checkout.Session.create.return_value = mock_session

        f = StripeCheckout(api_key="sk_test_fake")
        payload = Payload({
            "line_items": [],
            "success_url": "https://x.com/ok",
            "cancel_url": "https://x.com/no",
            "idempotency_key": "idem_abc",
        })
        asyncio.get_event_loop().run_until_complete(f.call(payload))
        call_kwargs = _mock_stripe.checkout.Session.create.call_args
        assert call_kwargs.kwargs["idempotency_key"] == "idem_abc"

    def test_subscription_mode(self):
        from codeupipe_stripe.checkout import StripeCheckout

        mock_session = SimpleNamespace(url="https://stripe.com/sub", id="cs_sub")
        _mock_stripe.checkout.Session.create.return_value = mock_session

        f = StripeCheckout(api_key="sk_test_fake")
        payload = Payload({
            "line_items": [{"price": "price_sub", "quantity": 1}],
            "success_url": "https://x.com/ok",
            "cancel_url": "https://x.com/no",
            "mode": "subscription",
        })
        asyncio.get_event_loop().run_until_complete(f.call(payload))
        call_kwargs = _mock_stripe.checkout.Session.create.call_args
        assert call_kwargs.kwargs["mode"] == "subscription"


# ── StripeSubscription ──────────────────────────────────────────────


class TestStripeSubscription:
    def test_create_subscription(self):
        from codeupipe_stripe.subscription import StripeSubscription

        mock_sub = SimpleNamespace(id="sub_789", status="active")
        _mock_stripe.Subscription.create.return_value = mock_sub

        f = StripeSubscription(api_key="sk_test_fake")
        payload = Payload({
            "action": "create",
            "customer_id": "cus_123",
            "price_id": "price_456",
        })
        result = asyncio.get_event_loop().run_until_complete(f.call(payload))
        sub = result.get("subscription")
        assert sub["id"] == "sub_789"
        assert sub["status"] == "active"

    def test_cancel_subscription(self):
        from codeupipe_stripe.subscription import StripeSubscription

        mock_sub = SimpleNamespace(id="sub_789", status="canceled")
        _mock_stripe.Subscription.delete.return_value = mock_sub

        f = StripeSubscription(api_key="sk_test_fake")
        payload = Payload({"action": "cancel", "subscription_id": "sub_789"})
        result = asyncio.get_event_loop().run_until_complete(f.call(payload))
        assert result.get("subscription")["status"] == "canceled"

    def test_retrieve_subscription(self):
        from codeupipe_stripe.subscription import StripeSubscription

        mock_sub = SimpleNamespace(id="sub_789", status="active")
        _mock_stripe.Subscription.retrieve.return_value = mock_sub

        f = StripeSubscription(api_key="sk_test_fake")
        payload = Payload({"action": "retrieve", "subscription_id": "sub_789"})
        result = asyncio.get_event_loop().run_until_complete(f.call(payload))
        assert result.get("subscription")["id"] == "sub_789"

    def test_unknown_action_raises(self):
        from codeupipe_stripe.subscription import StripeSubscription

        f = StripeSubscription(api_key="sk_test_fake")
        payload = Payload({"action": "explode"})
        with pytest.raises(ValueError, match="Unknown action"):
            asyncio.get_event_loop().run_until_complete(f.call(payload))


# ── StripeCustomer ──────────────────────────────────────────────────


class TestStripeCustomer:
    def test_create_customer(self):
        from codeupipe_stripe.customer import StripeCustomer

        mock_cust = SimpleNamespace(id="cus_aaa", email="test@example.com")
        _mock_stripe.Customer.create.return_value = mock_cust

        f = StripeCustomer(api_key="sk_test_fake")
        payload = Payload({"action": "create", "email": "test@example.com", "name": "Test"})
        result = asyncio.get_event_loop().run_until_complete(f.call(payload))
        cust = result.get("customer")
        assert cust["id"] == "cus_aaa"
        assert cust["email"] == "test@example.com"

    def test_retrieve_customer(self):
        from codeupipe_stripe.customer import StripeCustomer

        mock_cust = SimpleNamespace(id="cus_aaa", email="found@example.com")
        _mock_stripe.Customer.retrieve.return_value = mock_cust

        f = StripeCustomer(api_key="sk_test_fake")
        payload = Payload({"action": "retrieve", "customer_id": "cus_aaa"})
        result = asyncio.get_event_loop().run_until_complete(f.call(payload))
        assert result.get("customer")["email"] == "found@example.com"

    def test_unknown_action_raises(self):
        from codeupipe_stripe.customer import StripeCustomer

        f = StripeCustomer(api_key="sk_test_fake")
        payload = Payload({"action": "nope"})
        with pytest.raises(ValueError, match="Unknown action"):
            asyncio.get_event_loop().run_until_complete(f.call(payload))
