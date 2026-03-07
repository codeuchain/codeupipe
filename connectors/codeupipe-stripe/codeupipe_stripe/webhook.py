"""
StripeWebhook: Verify and parse incoming Stripe webhook events.

Reads 'webhook_payload' (raw body bytes) and 'webhook_signature' from payload.
Returns 'event_type' and 'event_data'.
"""

from codeupipe import Payload


class StripeWebhook:
    """Verify and parse Stripe webhook events."""

    def __init__(self, webhook_secret: str = None):
        self._webhook_secret = webhook_secret

    async def call(self, payload: Payload) -> Payload:
        import stripe

        raw_body = payload.get("webhook_payload", b"")
        signature = payload.get("webhook_signature", "")

        if self._webhook_secret:
            event = stripe.Webhook.construct_event(
                raw_body, signature, self._webhook_secret
            )
        else:
            event = stripe.Event.construct_from(
                stripe.util.json.loads(raw_body), stripe.api_key
            )

        return (
            payload
            .insert("event_type", event.type)
            .insert("event_data", dict(event.data.object))
        )
