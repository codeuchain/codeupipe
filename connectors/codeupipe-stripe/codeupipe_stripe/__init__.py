"""
codeupipe-stripe: Stripe connector package.

Filters:
- StripeCheckout: Create checkout sessions
- StripeSubscription: CRUD subscription management
- StripeWebhook: Verify + parse incoming webhook events
- StripeCustomer: Customer lookup/create
"""

from .checkout import StripeCheckout
from .subscription import StripeSubscription
from .webhook import StripeWebhook
from .customer import StripeCustomer


def register(registry, config):
    """Entry point called by codeupipe discover_connectors."""
    import stripe

    api_key = config.resolve_env("api_key_env")
    stripe.api_key = api_key

    registry.register(
        f"{config.name}_checkout",
        lambda: StripeCheckout(api_key=api_key),
        kind="connector",
        force=True,
    )
    registry.register(
        f"{config.name}_subscription",
        lambda: StripeSubscription(api_key=api_key),
        kind="connector",
        force=True,
    )

    webhook_secret = config.resolve_env("webhook_secret_env", required=False)
    registry.register(
        f"{config.name}_webhook",
        lambda: StripeWebhook(webhook_secret=webhook_secret),
        kind="connector",
        force=True,
    )
    registry.register(
        f"{config.name}_customer",
        lambda: StripeCustomer(api_key=api_key),
        kind="connector",
        force=True,
    )


__all__ = [
    "register",
    "StripeCheckout",
    "StripeSubscription",
    "StripeWebhook",
    "StripeCustomer",
]
