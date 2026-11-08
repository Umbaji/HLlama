"""Scheduling a reminder, deterministically.

The model only spots the request and copies what it heard (kind, date).
Everything after that happens here: ask for what is missing, parse it, show a
recap, and create the reminder only once she confirms. Nothing exists before
that, so the model can no longer announce a reminder that was never created.
"""
import logging
from datetime import datetime

from app.services import answers, recurrence, when_fr
from app.services.backend_client import backend_error, json_or_none, post_json, unwrap
from app.services.chat_state import reminder_drafts, reminder_snapshot
from app.services.local_time import now_local
from app.services.reminder_texts import (
    CANCEL_TITLE,
    CANCELLED_TEXT,
    CONFIRM_QUESTION,
    CONFIRM_TITLE,
    FOOTER,
    GAVE_UP_TEXT,
    INVALID_TEXTS,
    KIND_LABELS,
    KINDS,
    PAST_TEXT,
    QUESTIONS,
    UNAVAILABLE_TEXT,
)
from app.services.whatsapp_api import build_buttons_payload, get_text_message_input
from app.utils.anonymity import pseudo_id_for

BUTTON_PREFIX = "RMD:"
CONFIRM_ID = "RMD:OK"
CANCEL_ID = "RMD:NO"

MESSAGE_MAX_CHARS = 200
MAX_ATTEMPTS = 3

_EMPTY_VALUES = {"", "n/a", "na", "null", "none", "aucun", "aucune"}

def _clean(raw) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    return None if text.lower() in _EMPTY_VALUES else text


def _kind_of(structured: dict) -> str:
    kind = (_clean(structured.get("reminder_kind")) or "other").lower()
    return kind if kind in KINDS else "other"


def _repeat_days(raw) -> int | None:
    try:
        days = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return days if 1 <= days <= 365 else None


def _repeat_pattern(raw) -> str | None:
    """The pattern she named, when it is one the bot knows."""
    pattern = str(raw or "").strip().lower()
    return pattern if pattern in recurrence.PATTERNS else None


def _interval(draft: dict) -> int | None:
    """The interval the backend repeats on, None when the bot repeats itself."""
    return draft.get("repeat_days") or recurrence.interval_days(draft.get("repeat_pattern"))


def _repeat_label(draft: dict) -> str | None:
    """How the recurrence is said to her."""
    pattern = draft.get("repeat_pattern")
    if pattern == recurrence.MONTHLY:
        return f"Répété chaque mois ({recurrence.MONTHLY_OCCURRENCES} fois)"
    if pattern == recurrence.DAILY:
        return "Répété tous les jours"
    if pattern == recurrence.WEEKLY:
        return "Répété toutes les semaines"
    if draft.get("repeat_days"):
        return f"Répété tous les {draft['repeat_days']} jours"
    return None


SLOTS = ("message", "when")


def recap_text(draft: dict) -> str:
    label = KIND_LABELS.get(draft.get("kind"), KIND_LABELS["other"])
    when = draft["when"].strftime("%d/%m/%Y à %H:%M")
    lines = [f"{label} le {when} : « {draft['message']} »"]
    repeat = _repeat_label(draft)
    if repeat:
        lines.append(repeat)
    return "\n".join(lines) + f"\n\n{CONFIRM_QUESTION}"


def confirmation_text(draft: dict, created: int = 1) -> str:
    when = draft["when"].strftime("%d/%m/%Y à %H:%M")
    label = _repeat_label(draft)
    repeat = f", {label.lower()}" if label else ""
    dates = recurrence.occurrences(draft["when"], draft.get("repeat_pattern"))
    if len(dates) > 1 and created < len(dates):
        repeat = f", {created} fois sur {len(dates)}"
    return f"✅ Rappel programmé le {when}{repeat} : « {draft['message']} ». {FOOTER}"


def start_from_structured(wa_id: str, structured: dict, send) -> None:
    """Entry point for a `reminder` from the model."""
    message = _clean(structured.get("request_content"))
    draft = {
        "kind": _kind_of(structured),
        "message": message[:MESSAGE_MAX_CHARS] if message else None,
        "when": when_fr.parse_when(_clean(structured.get("scheduled_at")) or "", now_local(wa_id)),
        "repeat_days": _repeat_days(structured.get("repeat_interval_days")),
        "repeat_pattern": _repeat_pattern(structured.get("repeat_pattern")),
        "awaiting": None,
        "attempts": 0,
    }
    _advance(wa_id, draft, send)


def _advance(wa_id: str, draft: dict, send, notice: str | None = None) -> None:
    missing = next((slot for slot in SLOTS if not draft.get(slot)), None)
    if missing is None:
        _ask_confirmation(wa_id, draft, send)
        return
    draft["awaiting"] = missing
    reminder_drafts.set(pseudo_id_for(wa_id), draft)
    send(get_text_message_input(wa_id, notice or QUESTIONS[missing]))


def _ask_confirmation(wa_id: str, draft: dict, send) -> None:
    draft["awaiting"] = "confirmation"
    draft["attempts"] = 0
    reminder_drafts.set(pseudo_id_for(wa_id), draft)
    send(build_buttons_payload(wa_id, recap_text(draft), [
        (CONFIRM_ID, CONFIRM_TITLE),
        (CANCEL_ID, CANCEL_TITLE),
    ]))


def _payload(wa_id: str, draft: dict, when: datetime) -> dict:
    payload = {
        "pseudo_id": pseudo_id_for(wa_id),
        "telnumber": wa_id,
        "kind": draft["kind"],
        "message": draft["message"],
        "scheduled_at": when.isoformat(),
        "repeat_interval_days": _interval(draft),
    }
    return payload


def _create(wa_id: str, draft: dict, send) -> None:
    pseudo_id = pseudo_id_for(wa_id)
    dates = recurrence.occurrences(draft["when"], draft.get("repeat_pattern"))
    created = 0
    for index, when in enumerate(dates):
        response = post_json("/api/bot/reminders", _payload(wa_id, draft, when))
        if response is None or response.status_code >= 400:
            code, _ = backend_error(response)
            logging.warning(
                "Reminder refused: %s",
                code or ("no response" if response is None else f"HTTP {response.status_code}"),
            )
            if code == "REMINDER_IN_PAST" and index == 0:
                # Her date was right when she typed it, or the draft sat too
                # long: ask that one slot again instead of losing the reminder.
                draft["when"] = None
                draft["attempts"] = 0
                _advance(wa_id, draft, send, notice=f"{PAST_TEXT} {QUESTIONS['when']}")
                return
            if index == 0:
                reminder_drafts.pop(pseudo_id)
                send(get_text_message_input(wa_id, UNAVAILABLE_TEXT))
                return
            # The first ones are already there: say how many exist rather than
            # pretending the whole series was programmed.
            break
        created += 1
        item = unwrap(json_or_none(response))
        if not isinstance(item, dict) or not item.get("id"):
            logging.warning("Reminder created but the backend returned no id.")
    reminder_drafts.pop(pseudo_id)
    # The note the model is given must show the new reminder on her very next
    # message, not two minutes later.
    reminder_snapshot.pop(pseudo_id)
    send(get_text_message_input(wa_id, confirmation_text(draft, created)))


def consume_text(wa_id: str, text: str, send) -> bool:
    """Feeds her message to a reminder being prepared. Returns False when there
    is none, or when the message is clearly something else."""
    pseudo_id = pseudo_id_for(wa_id)
    draft = reminder_drafts.get(pseudo_id)
    if draft is None:
        return False
    answer = when_fr.normalize(text).rstrip(" !.")
    awaiting = draft.get("awaiting")

    if answers.is_cancel(answer) or (awaiting == "confirmation" and answers.is_no(answer)):
        reminder_drafts.pop(pseudo_id)
        send(get_text_message_input(wa_id, CANCELLED_TEXT))
        return True
    if awaiting == "confirmation":
        if answers.is_yes(answer):
            _create(wa_id, draft, send)
            return True
        # The recap buttons stay valid until expiry; anything else is a normal
        # message.
        return False

    raw = (text or "").strip()
    if awaiting == "message":
        if not raw:
            return True
        draft["message"] = raw[:MESSAGE_MAX_CHARS]
        _advance(wa_id, draft, send)
        return True

    value = when_fr.parse_when(raw, now_local(wa_id))
    if value is None:
        draft["attempts"] = draft.get("attempts", 0) + 1
        if draft["attempts"] >= MAX_ATTEMPTS:
            reminder_drafts.pop(pseudo_id)
            send(get_text_message_input(wa_id, GAVE_UP_TEXT))
            return True
        reminder_drafts.set(pseudo_id, draft)
        send(get_text_message_input(wa_id, INVALID_TEXTS[awaiting]))
        return True
    draft[awaiting] = value
    draft["attempts"] = 0
    _advance(wa_id, draft, send)
    return True


def handle_button(wa_id: str, button_id: str, send) -> None:
    pseudo_id = pseudo_id_for(wa_id)
    draft = reminder_drafts.get(pseudo_id)
    if draft is None:
        # The draft expired: say so rather than confirm a reminder nobody holds.
        send(get_text_message_input(wa_id, GAVE_UP_TEXT))
        return
    if button_id == CONFIRM_ID:
        _create(wa_id, draft, send)
        return
    reminder_drafts.pop(pseudo_id)
    send(get_text_message_input(wa_id, CANCELLED_TEXT))
