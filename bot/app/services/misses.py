"""The wording she used, kept without what she said.

The bot can only grow its services from what she really says, so the wordings
it did not understand are recorded. What is kept is the shape of a sentence:
the digits, the names and the links are removed, because a record of a person's
wording is not a record of their life.
"""
import logging
import re

from app.services.backend_client import post_json

LOGGER = logging.getLogger(__name__)

WORDING_MAX_CHARS = 200

_DIGITS = re.compile(r"\d+")
_LINK = re.compile(r"(https?://|www\.)\S+", re.IGNORECASE)
_EMAIL = re.compile(r"\S+@\S+")
_WHITESPACE = re.compile(r"\s{2,}")


def scrub(message: str, names: tuple[str, ...] = ()) -> str:
    """The shape of the sentence, without its content."""
    text = (message or "").strip()
    for name in names:
        if name and len(name) > 2:
            text = re.sub(re.escape(name), " ", text, flags=re.IGNORECASE)
    text = _LINK.sub(" ", text)
    text = _EMAIL.sub(" ", text)
    text = _DIGITS.sub("#", text)
    text = _WHITESPACE.sub(" ", text).strip()
    return text[:WORDING_MAX_CHARS].strip()


def log_miss(message: str, service: str | None, names: tuple[str, ...] = ()) -> None:
    """Records a wording the bot did not understand.

    A failure is not worth a message to her: the record is for the team, and
    the bot carries on.
    """
    wording = scrub(message, names)
    if not wording:
        return
    payload = {"service": service, "wording": wording, "language": "fr"}
    response = post_json("/api/bot/service-misses", payload)
    if response is None or response.status_code >= 400:
        LOGGER.warning(
            "Service miss not recorded: %s",
            "no response" if response is None else f"HTTP {response.status_code}",
        )
