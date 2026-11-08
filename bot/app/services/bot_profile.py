import logging
import os

import requests

from app.services.preferred_name import extract_preferred_name
from app.utils.anonymity import pseudo_id_for


LOGGER = logging.getLogger(__name__)
PROFILE_TIMEOUT = (1.5, 3.0)


def _headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-Bot-Api-Key": os.getenv("BOT_API_KEY", ""),
    }


def _profile_url(wa_id: str) -> str:
    base_url = os.getenv("NEAREST_API_URL", "").rstrip("/")
    return f"{base_url}/api/bot/users/{pseudo_id_for(wa_id)}/profile"


def _preferred_name(response: requests.Response) -> str | None:
    if response.status_code != 200:
        return None
    payload = response.json()
    data = payload.get("data") if isinstance(payload, dict) else None
    value = data.get("preferred_name") if isinstance(data, dict) else None
    return value if isinstance(value, str) and value.strip() else None


def fetch_preferred_name(wa_id: str) -> str | None:
    try:
        response = requests.get(
            _profile_url(wa_id),
            headers=_headers(),
            timeout=PROFILE_TIMEOUT,
        )
        return _preferred_name(response)
    except (ValueError, requests.RequestException):
        LOGGER.warning("Bot profile read failed; continuing anonymously")
        return None


def save_preferred_name(wa_id: str, preferred_name: str) -> str | None:
    try:
        response = requests.put(
            _profile_url(wa_id),
            headers=_headers(),
            json={"telnumber": wa_id, "preferred_name": preferred_name},
            timeout=PROFILE_TIMEOUT,
        )
        return _preferred_name(response)
    except (ValueError, requests.RequestException):
        LOGGER.warning("Bot profile update failed; continuing anonymously")
        return None


def resolve_preferred_name(wa_id: str, message: str) -> str | None:
    supplied_name = extract_preferred_name(message)
    if supplied_name:
        persisted_name = save_preferred_name(wa_id, supplied_name)
        if persisted_name:
            return persisted_name
    return fetch_preferred_name(wa_id)
