"""Bot-side anonymisation helpers.

Mirror of the backend `helpers/anonymity.py`: computes the same deterministic
`pseudo_id` from a WhatsApp `wa_id` so the bot can identify users without ever
sending raw phone numbers in API calls.

The shared `PSEUDO_ID_SECRET` must be identical to the backend's, otherwise
the backend cannot resolve the user.
"""
import hashlib
import hmac
import os
import re

from app.config import require_pseudo_id_secret


def pseudo_id_for(wa_id: str | None) -> str:
    """Deterministic pseudonymous identifier, HMAC-SHA256(secret, digits)."""
    secret = require_pseudo_id_secret(os.getenv("PSEUDO_ID_SECRET"))
    digits = re.sub(r"\D", "", wa_id or "")
    if not digits:
        return ""
    return hmac.new(
        secret.encode("utf-8"),
        digits.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]
