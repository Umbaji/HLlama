"""Moving a reminder she already has.

"Décale le rappel 2 à jeudi" was impossible: the flow could create a reminder,
list them and cancel one by number, but nothing could touch a reminder that
existed. The message reached the model as a question and the model answered
from imagination.

The model says which reminder (the numbered note gives it the number she used)
and to when; the bot recreates the reminder with the same content at the new
date, then cancels the old one. She is never left without the reminder she
asked for, not even for a second, and nothing changes before she confirms.
"""
import logging

from app import reminder_agent
from app.services import answers, when_fr
from app.services.backend_client import json_or_none, post_json, unwrap
from app.services.chat_state import reminder_update_drafts
from app.services.local_time import now_local
from app.services.reminder_status import cancel_user_reminder, reminders_last_shown
from app.services.reminder_texts import SHORT_KIND_LABELS
from app.services.whatsapp_api import build_buttons_payload, get_text_message_input
from app.utils.anonymity import pseudo_id_for

BUTTON_PREFIX = "RMU:"
CONFIRM_ID = "RMU:OK"
CANCEL_ID = "RMU:NO"

MAX_ATTEMPTS = 3

QUESTIONS = {
    "target": "Lequel ? Écrivez le numéro du rappel à déplacer.",
    "when": (
        "Quelle nouvelle date ? Vous pouvez écrire « demain à 20h », "
        "« le 25/10 à 8h » ou « dans 3 jours »."
    ),
}

INVALID_TEXTS = {
    "target": "Je n'ai pas compris le numéro du rappel. Écrivez le numéro, par exemple 2.",
    "when": (
        "Je n'ai pas compris la date. Écrivez par exemple « demain à 20h », "
        "« le 25/10 à 8h » ou « dans 3 jours »."
    ),
}

GAVE_UP_TEXT = "D'accord, j'ai laissé ton rappel tel quel."
CANCELLED_TEXT = "D'accord, je n'ai rien déplacé."
CONFIRM_QUESTION = "Je le décale ?"
CONFIRM_TITLE = "Confirmer"
CANCEL_TITLE = "Annuler"
UNAVAILABLE_TEXT = (
    "Je n'ai pas pu déplacer ce rappel (service momentanément indisponible). "
    "Réessayez dans quelques minutes."
)
NOT_FOUND_TEXT = (
    "Je ne vois pas de rappel avec ce numéro dans la liste que je vous ai montrée. "
    "Écrivez « mes rappels » pour la revoir."
)


def _label(reminder: dict) -> str:
    return SHORT_KIND_LABELS.get(reminder.get("kind"), SHORT_KIND_LABELS["other"])


def _when_text(value) -> str:
    return reminder_agent.format_local_date(value, None)


def recap_text(draft: dict) -> str:
    reminder = draft["reminder"]
    old = _when_text(reminder.get("scheduled_at"))
    new = draft["when"].strftime("%d/%m/%Y à %H:%M")
    return (
        f"Je décale « {_label(reminder)} » du {old} au {new}.\n\n"
        f"{CONFIRM_QUESTION}"
    )


def confirmation_text(draft: dict) -> str:
    reminder = draft["reminder"]
    new = draft["when"].strftime("%d/%m/%Y à %H:%M")
    return f"C'est fait : « {_label(reminder)} » est maintenant prévu le {new}."


def _payload(wa_id: str, draft: dict) -> dict:
    """The new reminder: the same content, at the new date."""
    reminder = draft["reminder"]
    payload = {
        "pseudo_id": pseudo_id_for(wa_id),
        "telnumber": wa_id,
        "kind": reminder.get("kind") or "other",
        "message": reminder.get("message") or "",
        "scheduled_at": draft["when"].isoformat(),
        "repeat_interval_days": reminder.get("repeat_interval_days"),
    }
    return payload


def _create(wa_id: str, draft: dict, send) -> bool:
    """The new reminder first: she must never be left without it."""
    response = post_json("/api/bot/reminders", _payload(wa_id, draft))
    if response is None or response.status_code >= 400:
        logging.warning(
            "Reminder update refused: %s",
            "no response" if response is None else f"HTTP {response.status_code}",
        )
        return False
    created = unwrap(json_or_none(response))
    if not isinstance(created, dict) or not created.get("id"):
        logging.warning("Reminder created but the backend returned no id.")
    return True


def start_from_structured(wa_id: str, structured: dict, send) -> None:
    """Entry point for a `reminder_update` from the model."""
    number = structured.get("reminder_number")
    try:
        number = int(number) if number is not None else None
    except (TypeError, ValueError):
        number = None
    raw_when = structured.get("scheduled_at")
    draft = {
        "reminder": None,
        "number": number,
        "when": when_fr.parse_when(str(raw_when or ""), now_local(wa_id)) if raw_when else None,
        "awaiting": None,
        "attempts": 0,
    }
    _advance(wa_id, draft, send)


def _resolve(wa_id: str, draft: dict) -> dict | None:
    """The reminder at the position she named, in the list she was shown."""
    number = draft.get("number")
    if not number:
        return None
    last = reminders_last_shown(wa_id)
    if not 1 <= number <= len(last):
        return None
    return last[number - 1]


def _advance(wa_id: str, draft: dict, send, notice: str | None = None) -> None:
    if draft.get("reminder") is None:
        draft["reminder"] = _resolve(wa_id, draft)
    if draft.get("reminder") is None:
        if draft.get("number"):
            send(get_text_message_input(wa_id, NOT_FOUND_TEXT))
            reminder_update_drafts.pop(pseudo_id_for(wa_id))
            return
        draft["awaiting"] = "target"
        reminder_update_drafts.set(pseudo_id_for(wa_id), draft)
        send(get_text_message_input(wa_id, notice or QUESTIONS["target"]))
        return
    if draft.get("when") is None:
        draft["awaiting"] = "when"
        reminder_update_drafts.set(pseudo_id_for(wa_id), draft)
        send(get_text_message_input(wa_id, notice or QUESTIONS["when"]))
        return
    draft["awaiting"] = "confirmation"
    draft["attempts"] = 0
    reminder_update_drafts.set(pseudo_id_for(wa_id), draft)
    send(build_buttons_payload(wa_id, recap_text(draft), [
        (CONFIRM_ID, CONFIRM_TITLE),
        (CANCEL_ID, CANCEL_TITLE),
    ]))


def _apply(wa_id: str, draft: dict, send) -> None:
    """Create the new reminder, then cancel the old one."""
    reminder_update_drafts.pop(pseudo_id_for(wa_id))
    if not _create(wa_id, draft, send):
        send(get_text_message_input(wa_id, UNAVAILABLE_TEXT))
        return
    old_id = draft["reminder"].get("id")
    cancelled = cancel_user_reminder(wa_id, old_id) if old_id else None
    if cancelled is None:
        # The new one exists, the old one still does: she must know she has two.
        send(get_text_message_input(wa_id, (
            "Le nouveau rappel est programmé, mais je n'ai pas pu annuler "
            "l'ancien : tu as donc les deux. Écris « mes rappels » pour les voir."
        )))
        return
    send(get_text_message_input(wa_id, confirmation_text(draft)))


def _number_from(text: str) -> int | None:
    digits = "".join(char for char in (text or "") if char.isdigit())
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def consume_text(wa_id: str, text: str, send) -> bool:
    """Feeds her message to the move being prepared."""
    pseudo_id = pseudo_id_for(wa_id)
    draft = reminder_update_drafts.get(pseudo_id)
    if draft is None:
        return False
    answer = when_fr.normalize(text).rstrip(" !.")
    awaiting = draft.get("awaiting")

    if answers.is_cancel(answer) or (awaiting == "confirmation" and answers.is_no(answer)):
        reminder_update_drafts.pop(pseudo_id)
        send(get_text_message_input(wa_id, CANCELLED_TEXT))
        return True
    if awaiting == "confirmation":
        if answers.is_yes(answer):
            _apply(wa_id, draft, send)
            return True
        return False

    raw = (text or "").strip()
    if awaiting == "target":
        value = _number_from(raw)
        if value is None:
            draft["attempts"] = draft.get("attempts", 0) + 1
            if draft["attempts"] >= MAX_ATTEMPTS:
                reminder_update_drafts.pop(pseudo_id)
                send(get_text_message_input(wa_id, GAVE_UP_TEXT))
                return True
            reminder_update_drafts.set(pseudo_id, draft)
            send(get_text_message_input(wa_id, INVALID_TEXTS["target"]))
            return True
        draft["number"] = value
    else:
        value = when_fr.parse_when(raw, now_local(wa_id))
        if value is None:
            draft["attempts"] = draft.get("attempts", 0) + 1
            if draft["attempts"] >= MAX_ATTEMPTS:
                reminder_update_drafts.pop(pseudo_id)
                send(get_text_message_input(wa_id, GAVE_UP_TEXT))
                return True
            reminder_update_drafts.set(pseudo_id, draft)
            send(get_text_message_input(wa_id, INVALID_TEXTS["when"]))
            return True
    draft[awaiting] = value
    draft["attempts"] = 0
    _advance(wa_id, draft, send)
    return True


def handle_button(wa_id: str, button_id: str, send) -> None:
    pseudo_id = pseudo_id_for(wa_id)
    draft = reminder_update_drafts.get(pseudo_id)
    if draft is None:
        send(get_text_message_input(wa_id, GAVE_UP_TEXT))
        return
    if button_id == CONFIRM_ID:
        _apply(wa_id, draft, send)
        return
    reminder_update_drafts.pop(pseudo_id)
    send(get_text_message_input(wa_id, CANCELLED_TEXT))
