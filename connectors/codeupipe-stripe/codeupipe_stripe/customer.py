"""
StripeCustomer: Customer lookup and creation.

Reads 'email' + optional 'name' for create.
Reads 'customer_id' for retrieve.
Returns 'customer' dict.
"""

from codeupipe import Payload


class StripeCustomer:
    """Manage Stripe customers."""

    def __init__(self, api_key: str):
        self._api_key = api_key

    async def call(self, payload: Payload) -> Payload:
        import stripe

        action = payload.get("action", "create")

        if action == "create":
            email = payload.get("email")
            name = payload.get("name", None)
            kwargs = {"email": email, "api_key": self._api_key}
            if name:
                kwargs["name"] = name
            customer = stripe.Customer.create(**kwargs)
            return payload.insert("customer", {"id": customer.id, "email": customer.email})

        if action == "retrieve":
            customer_id = payload.get("customer_id")
            customer = stripe.Customer.retrieve(customer_id, api_key=self._api_key)
            return payload.insert("customer", {"id": customer.id, "email": customer.email})

        raise ValueError(f"Unknown action: {action}")
