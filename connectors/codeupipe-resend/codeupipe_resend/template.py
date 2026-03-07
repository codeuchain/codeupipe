"""
ResendTemplate: Send using a Resend template with variables.

Reads 'to', 'template_id', 'variables' from payload.
Returns 'email_id'.
"""

from codeupipe import Payload


class ResendTemplate:
    """Send an email using a Resend template."""

    def __init__(self, api_key: str, default_from: str = None):
        self._api_key = api_key
        self._default_from = default_from

    async def call(self, payload: Payload) -> Payload:
        import resend

        resend.api_key = self._api_key

        to = payload.get("to", [])
        if isinstance(to, str):
            to = [to]
        from_addr = payload.get("from_address", self._default_from)
        subject = payload.get("subject", "")

        params = {
            "from_": from_addr,
            "to": to,
            "subject": subject,
        }

        # Template rendering: Resend supports react or HTML templates
        # We pass template data as HTML with variables pre-resolved
        template_id = payload.get("template_id", None)
        variables = payload.get("variables", {})

        # Resend's template rendering — pass variables via headers or HTML
        html = payload.get("html", "")
        for key, value in variables.items():
            html = html.replace(f"{{{{{key}}}}}", str(value))
        params["html"] = html

        result = resend.Emails.send(params)

        email_id = result.get("id") if isinstance(result, dict) else getattr(result, "id", None)
        return payload.insert("email_id", email_id)
