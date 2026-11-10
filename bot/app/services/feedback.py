"""Feedback questions after use (contract section 3).

Two questions at most: `usefulness` through three reply buttons, then an
optional free-text `comment` asked once. The bot only asks and forwards the
answers.
"""
import logging

from app.services.backend_client import post_json
from app.services.chat_state import feedback_comment_asked, feedback_comment_pending
from app.services.whatsapp_api import build_buttons_payload, get_text_message_input
from app.utils.anonymity import pseudo_id_for

USEFULNESS_QUESTION = (
    "Petite question de HLlama : nos échanges vous ont-ils été utiles ?"
)
USEFULNESS_BUTTONS = [
    ("FB:usefulness:3", "Utile"),
    ("FB:usefulness:2", "Moyen"),
    ("FB:usefulness:1", "Pas utile"),
]
COMMENT_QUESTION = "Un commentaire pour nous améliorer ? Répondez ou ignorez ce message."
THANKS_TEXT = "Merci pour votre retour \U0001F49B"
COMMENT_THANKS_TEXT = "Merci, votre commentaire a bien été transmis \U0001F49B"

ANSWER_MAX_CHARS = 500
_QUESTION_RATINGS = {"usefulness": {1, 2, 3}}


def usefulness_payload(wa_id: str) -> dict:
    return build_buttons_payload(wa_id, USEFULNESS_QUESTION, USEFULNESS_BUTTONS)


def submit_feedback(wa_id: str, question_key: str, rating: int | None = None, answer: str | None = None) -> bool:
    response = post_json("/api/bot/feedback", {
        "pseudo_id": pseudo_id_for(wa_id),
        "question_key": question_key,
        "rating": rating,
        "answer": answer[:ANSWER_MAX_CHARS] if answer else None,
    })
    if response is None or response.status_code >= 400:
        logging.error(
            "Feedback submit failed: %s",
            "no response" if response is None else f"HTTP {response.status_code}",
        )
        return False
    return True


def parse_feedback_button(button_id: str) -> tuple[str, int] | None:
    """`FB:<key>:<value>` -> (key, rating), or None when malformed."""
    parts = (button_id or "").split(":")
    if len(parts) != 3 or parts[0] != "FB":
        return None
    key, raw_value = parts[1], parts[2]
    try:
        value = int(raw_value)
    except ValueError:
        return None
    if value not in _QUESTION_RATINGS.get(key, set()):
        return None
    return key, value


def handle_feedback_button(wa_id: str, button_id: str, send) -> None:
    parsed = parse_feedback_button(button_id)
    if parsed is None:
        logging.warning("Ignoring malformed feedback button.")
        return
    key, rating = parsed
    submit_feedback(wa_id, key, rating=rating)
    pseudo_id = pseudo_id_for(wa_id)
    send(get_text_message_input(wa_id, THANKS_TEXT))
    if pseudo_id in feedback_comment_asked:
        return
    feedback_comment_asked.set(pseudo_id)
    feedback_comment_pending.set(pseudo_id)
    send(get_text_message_input(wa_id, COMMENT_QUESTION))


def consume_feedback_comment(wa_id: str, text: str, send) -> bool:
    """Stores `text` as the feedback comment when the user was just asked for
    one. Returns True when the message was consumed that way."""
    pseudo_id = pseudo_id_for(wa_id)
    if feedback_comment_pending.pop(pseudo_id) is None:
        return False
    comment = (text or "").strip()
    if not comment:
        return False
    submit_feedback(wa_id, "comment", answer=comment)
    send(get_text_message_input(wa_id, COMMENT_THANKS_TEXT))
    return True
