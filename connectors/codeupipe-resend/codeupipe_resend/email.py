"""
ResendEmail: Send a single transactional email.

Reads 'to', 'subject', 'html' (or 'text') from payload.
Optional 'from_address' overrides the default.
Returns 'email_id'.
"""

from codeupipe import Payload


class ResendEmail:
    """Send a transactional email via Resend."""

    def __init__(self, api_key: str, default_from: str = None):
        self._api_key = api_key
        self._default_from = default_from

    async def call(self, payload: Payload) -> Payload:
        import resend

        resend.api_key = self._api_key

        to = payload.get("to", [])
        if isinstance(to, str):
            to = [to]
        subject = payload.get("subject", "")
        from_addr = payload.get("from_address", self._default_from)
        html = payload.get("html", None)
        text = payload.get("text", None)

        params = {
            "from_": from_addr,
            "to": to,
            "subject": subject,
        }
        if html:
            params["html"] = html
        elif text:
            params["text"] = text

        result = resend.Emails.send(params)

        email_id = result.get("id") if isinstance(result, dict) else getattr(result, "id", None)
        return payload.insert("email_id", email_id)
