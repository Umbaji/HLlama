"""Anonymisation helpers for the HLlama platform.

Privacy model (tokenisation complète):
- Users are never looked up by their raw phone number.
- `pseudo_id` is a deterministic, keyed digest of the phone number
  (HMAC-SHA256 with `PSEUDO_ID_SECRET`), used as the stable identifier
  between the bot and the backend. Same number => same pseudo_id, but the
  number itself cannot be recovered from the pseudo_id.
- Phone numbers are encrypted at rest (Fernet, key derived from the same
  secret) so a database dump leaks no PII.
- Admin-facing output only ever exposes `pseudo_id` + a masked number.
"""
import base64
import hashlib
import hmac
import re

from cryptography.fernet import Fernet

from config import settings


def normalize_number(number: str | None) -> str:
    """Normalizes a phone number to a comparable digit string (E.164-ish).

    WhatsApp wa_ids arrive as bare digits (e.g. "22890000100"), backend
    stored values may carry "+", spaces or dashes. We strip everything that
    is not a digit so both sides always hash the same canonical string.
    """
    if not number:
        return ""
    return re.sub(r"\D", "", number)


def pseudo_id_for(number: str | None) -> str:
    """Deterministic pseudonymous identifier for a phone number.

    HMAC-SHA256(secret, normalized_digits) -> hex string. The digest is
    truncated to 32 hex chars (128 bits) for compactness; collisions are
    negligible at platform scale.
    """
    digits = normalize_number(number)
    if not digits:
        raise ValueError("NUMBER_REQUIRED")
    return hmac.new(
        settings.PSEUDO_ID_SECRET.encode(),
        digits.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]


def _fernet() -> Fernet:
    """Builds a Fernet cipher whose key is derived from PSEUDO_ID_SECRET.

    Deriving the key from the same secret the bot shares keeps the whole
    anonymisation scheme governed by a single value. SHA-256 gives the
    32 bytes Fernet needs; base64 makes it url-safe.
    """
    digest = hashlib.sha256(settings.PSEUDO_ID_SECRET.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_number(number: str | None) -> str | None:
    """Encrypts a phone number for storage at rest. Returns None for empty."""
    digits = normalize_number(number)
    if not digits:
        return None
    return _fernet().encrypt(digits.encode("utf-8")).decode("utf-8")


def decrypt_number(token: str | None) -> str | None:
    """Decrypts a stored number, or None when the token is missing/invalid."""
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except Exception:
        return None


def encrypt_personal_text(value: str | None) -> str | None:
    """Encrypts optional personal text without normalizing its contents."""
    text = (value or "").strip()
    if not text:
        return None
    return _fernet().encrypt(text.encode("utf-8")).decode("utf-8")


def decrypt_personal_text(token: str | None) -> str | None:
    """Decrypts personal text, returning None for missing or invalid data."""
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except Exception:
        return None


def mask_number(number: str | None) -> str | None:
    """Returns a masked display form (last 4 digits) for admin interfaces."""
    digits = normalize_number(number)
    if not digits:
        return None
    if len(digits) <= 4:
        return f"••••{digits}"
    return f"••••{digits[-4:]}"


def blind_index(number: str | None) -> str | None:
    """A deterministic, keyed index of a number, to look it up without storing it.

    The number itself is encrypted at rest, so it cannot be queried. This is the
    other half of the same key: HMAC-SHA256(secret, digits) gives a value that
    can be indexed and compared, and that reveals nothing without the secret.
    It is what makes "who is this number?" answerable without decrypting every
    row.
    """
    digits = normalize_number(number)
    if not digits:
        return None
    return hmac.new(
        settings.PSEUDO_ID_SECRET.encode(),
        f"recipient:{digits}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]
