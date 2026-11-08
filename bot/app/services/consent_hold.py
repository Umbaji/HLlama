"""The request the consent gate turned away.

She writes something precise — "Envoie 2000 F à 90000100 pour des médicaments" —
the gate asks her to consent first, and her request is gone. She has to type it
again after the form, which is where people give up. It is kept here instead,
and replayed once she may be served.
"""
import logging
import re

from app.services.chat_state import held_request
from app.utils.anonymity import pseudo_id_for

INTRO = "Je reprends votre demande de tout à l'heure :"
KEPT_NOTICE = "Je garde votre demande, je m'en occupe juste après \U0001F49B"
MAX_CHARS = 1000

# A message with nothing to act on: a greeting, a thank-you, "c'est fait" after
# the form. Kept, it would be replayed as a request ("Je reprends votre demande
# : « Hello »") and answered on its own, out of context.
_SMALL_TALK_RE = re.compile(
    r"^(?:hello|hi|hey|coucou|cc|salut|slt|bonjour|bjr|bonsoir|bsr|allo|allô|yo"
    r"|ok|okay|oui|d['’]accord|dac|merci|c['’ ]est fait|voil[aà]|j['’]ai accept[ée])"
    r"(?:\s+hllama)?"
    r"[\s!.?,\U0001F300-\U0001FAFF\u2600-\u27BF]*$",
    re.IGNORECASE,
)


def _text_of(message: dict) -> str | None:
    if message.get("type") != "text":
        return None
    return (message.get("text", {}).get("body") or "").strip()


def is_small_talk(body: str) -> bool:
    return bool(_SMALL_TALK_RE.match(body.strip()))


def hold(wa_id: str, message: dict, confirmation_texts=()) -> bool:
    """Keep a text request. Returns whether something was kept.

    Anything other than plain text is dropped: a location or a voice note means
    nothing once its moment has passed. The consent confirmation itself is never
    kept, or it would be replayed at her as a request.
    """
    body = _text_of(message)
    if not body or body in confirmation_texts or is_small_talk(body):
        return False
    held_request.set(pseudo_id_for(wa_id), body[:MAX_CHARS])
    return True


def supersedes(message: dict, confirmation_texts=()) -> bool:
    """Whether the message she just sent replaces the kept request.

    A new request typed after the form is what she wants now: replaying the old
    one first gave her two answers in a row, the first to something she had
    moved on from. A button, a voice note, the form's confirmation or small talk
    ("c'est fait", "ok") carries no new request, so the kept one is replayed.
    """
    body = _text_of(message)
    return bool(body) and body not in confirmation_texts and not is_small_talk(body)


def discard(wa_id: str) -> None:
    held_request.pop(pseudo_id_for(wa_id))


def replay(wa_id: str, send_text, handle_text) -> bool:
    """Announce the kept request and hand it back to the normal handling."""
    body = held_request.pop(pseudo_id_for(wa_id))
    if not isinstance(body, str) or not body:
        return False
    send_text(f"{INTRO} « {body} »")
    try:
        handle_text(body)
    except Exception:
        logging.exception("Could not replay the held request")
    return True
