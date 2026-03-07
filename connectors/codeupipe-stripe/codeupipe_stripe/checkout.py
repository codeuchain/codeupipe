"""
StripeCheckout: Create Stripe checkout sessions.

Reads 'line_items', 'success_url', 'cancel_url' from payload.
Returns 'checkout_url' and 'session_id'.
"""

from codeupipe import Payload


class StripeCheckout:
    """Create a Stripe Checkout Session."""

    def __init__(self, api_key: str):
        self._api_key = api_key

    async def call(self, payload: Payload) -> Payload:
        import stripe

        line_items = payload.get("line_items", [])
        success_url = payload.get("success_url", "")
        cancel_url = payload.get("cancel_url", "")
        mode = payload.get("mode", "payment")
        idempotency_key = payload.get("idempotency_key", None)

        kwargs = {
            "line_items": line_items,
            "mode": mode,
            "success_url": success_url,
            "cancel_url": cancel_url,
        }

        session = stripe.checkout.Session.create(
            api_key=self._api_key,
            idempotency_key=idempotency_key,
            **kwargs,
        )

        return payload.insert("checkout_url", session.url).insert("session_id", session.id)
