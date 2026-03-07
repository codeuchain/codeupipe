"""
codeupipe-resend: Resend email connector package.

Filters:
- ResendEmail: Send a single transactional email
- ResendTemplate: Send using a Resend template with variables
"""

from .email import ResendEmail
from .template import ResendTemplate


def register(registry, config):
    """Entry point called by codeupipe discover_connectors."""
    import resend

    api_key = config.resolve_env("api_key_env")
    resend.api_key = api_key

    default_from = config.get("from_address", None)

    registry.register(
        f"{config.name}_email",
        lambda: ResendEmail(api_key=api_key, default_from=default_from),
        kind="connector",
        force=True,
    )
    registry.register(
        f"{config.name}_template",
        lambda: ResendTemplate(api_key=api_key, default_from=default_from),
        kind="connector",
        force=True,
    )


__all__ = [
    "register",
    "ResendEmail",
    "ResendTemplate",
]
