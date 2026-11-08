import hmac
from typing import Any


def extract_target_phone_number_id(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None

    entries = payload.get("entry")
    if not isinstance(entries, list) or not entries:
        return None

    entry = entries[0]
    if not isinstance(entry, dict):
        return None

    changes = entry.get("changes")
    if not isinstance(changes, list) or not changes:
        return None

    change = changes[0]
    if not isinstance(change, dict):
        return None

    value = change.get("value")
    if not isinstance(value, dict):
        return None

    metadata = value.get("metadata")
    if not isinstance(metadata, dict):
        return None

    phone_number_id: Any = metadata.get("phone_number_id")
    return phone_number_id if isinstance(phone_number_id, str) else None


def event_targets_configured_phone(
    payload: object,
    configured_phone_number_id: str | None,
) -> bool | None:
    target_phone_number_id = extract_target_phone_number_id(payload)
    if target_phone_number_id is None:
        return None
    if not configured_phone_number_id:
        return False
    return hmac.compare_digest(target_phone_number_id, configured_phone_number_id)
