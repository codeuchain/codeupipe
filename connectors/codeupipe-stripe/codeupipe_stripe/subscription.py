"""
StripeSubscription: CRUD subscription management.

Reads 'customer_id', 'price_id' from payload for create.
Reads 'subscription_id' for retrieve/cancel.
Returns 'subscription' dict.
"""

from codeupipe import Payload


class StripeSubscription:
    """Manage Stripe subscriptions."""

    def __init__(self, api_key: str):
        self._api_key = api_key

    async def call(self, payload: Payload) -> Payload:
        import stripe

        action = payload.get("action", "create")

        if action == "create":
            customer_id = payload.get("customer_id")
            price_id = payload.get("price_id")
            sub = stripe.Subscription.create(
                api_key=self._api_key,
                customer=customer_id,
                items=[{"price": price_id}],
            )
            return payload.insert("subscription", {"id": sub.id, "status": sub.status})

        if action == "retrieve":
            sub_id = payload.get("subscription_id")
            sub = stripe.Subscription.retrieve(sub_id, api_key=self._api_key)
            return payload.insert("subscription", {"id": sub.id, "status": sub.status})

        if action == "cancel":
            sub_id = payload.get("subscription_id")
            sub = stripe.Subscription.delete(sub_id, api_key=self._api_key)
            return payload.insert("subscription", {"id": sub.id, "status": sub.status})

        raise ValueError(f"Unknown action: {action}")
