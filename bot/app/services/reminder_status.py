"""Factual answers about the user's own reminders: list and targeted cancel.

The LLM proved unreliable at the empty state (« je ne vois pas de rappel » when
there were none to show only because it had no data), so these replies never go
through the model. The list is read straight from the backend through the
pseudo_id, formatted here, and « annule le rappel N » resolves the number
against the list that was actually shown to her.

The reminder id travels in a button id or in the path; the number never does.
"""
import json
import logging
import re

from app import reminder_agent
from app.services.backend_client import get_json, post_json, unwrap
from app.services.chat_state import reminder_last_list, reminder_snapshot
from app.services.reminder_texts import SHORT_KIND_LABELS
from app.services.whatsapp_api import build_buttons_payload, get_text_message_input
from app.utils.anonymity import pseudo_id_for

LOGGER = logging.getLogger(__name__)

CANCEL_BUTTON_TITLE = "Annuler le rappel {n}"

NO_REMINDERS_TEXT = "Vous n'avez aucun rappel en attente."
LIST_HEADER = "Voici vos rappels en attente :"
LIST_FOOTER = "Pour annuler l'un d'eux, répondez « annule le rappel <numéro> »."
CANCEL_UNKNOWN_TEXT = (
    "Je ne vois pas de rappel avec ce numéro dans la liste que je vous ai montrée. "
    "Écrivez « mes rappels » pour la revoir."
)
CANCEL_ERROR_TEXT = (
    "Je n'ai pas pu annuler ce rappel (service momentanément indisponible). "
    "Réessayez dans quelques minutes."
)
LIST_UNAVAILABLE_TEXT = (
    "Je n'ai pas pu consulter vos rappels (service momentanément indisponible). "
    "Réessayez dans quelques minutes."
)
CONFIRM_CANCELLED_TEXT = "D'accord, j'ai annulé « {label} » ({when})."
CONFIRM_CANCELLED_NO_WHEN_TEXT = "D'accord, j'ai annulé « {label} »."

# "Quels sont mes rappels ?", "rappels en attente", "liste de mes rappels"…
# Only *short* messages are served factually: a longer sentence is a question
# for the model, and the reminder opt-out ("annule tout") is handled separately.
LIST_REQUEST_RE = re.compile(
    r"^(?:"
    r"quels? (?:sont )?(?:mes|les|tous) rappels?(?: en attente)?"
    r"|tous? mes rappels?(?: en attente)?"
    r"|(?:mes|les) rappels?(?: en attente)?"
    r"|liste (?:de (?:mes|les|tous) )?rappels?"
    r"|rappels? en attente"
    r")\s*[?.!]*$",
    re.IGNORECASE,
)
# "annule le rappel 2", "annuler le rappel numéro 3" — an explicit number,
# never a bare "annule" (that is the global opt-out). The number may carry a
# trailing marker ("2 svp", "numéro 3").
CANCEL_ONE_RE = re.compile(
    r"\bannul(?:e|er|es)\b.*\brappel(?:s)?\b.*?(?:num[eé]ro\s*)?(\d+)[?.!]*\s*(?:s?vp|sil te plait|s\'il vous plaît)?$",
    re.IGNORECASE,
)


def _normalize_label(kind: str) -> str:
    return SHORT_KIND_LABELS.get(kind, SHORT_KIND_LABELS["other"])


def _line(reminder: dict, number: int) -> str:
    label = _normalize_label(reminder.get("kind"))
    when = reminder_agent.format_local_date(reminder.get("scheduled_at"), None)
    return f"{number}. {label}{f' — {when}' if when else ''}"


def _confirm_cancel(reminder: dict | None) -> str:
    if reminder is None:
        return CANCEL_UNKNOWN_TEXT
    label = _normalize_label(reminder.get("kind"))
    when = reminder_agent.format_local_date(reminder.get("scheduled_at"), None)
    if when:
        return CONFIRM_CANCELLED_TEXT.format(label=label, when=when)
    return CONFIRM_CANCELLED_NO_WHEN_TEXT.format(label=label)


# "Vous avez un nouveau message de HLlama" is deliberately empty: the detail
# follows on her next message. She often asks for it in words rather than by
# replying to the notice, and that question used to reach the model, which
# redirected her to health topics instead of showing anything.
DETAIL_REQUEST_RE = re.compile(
    r"^(?:"
    r"(?:c (?:est|etait) )?quoi (?:le|ce|votre) message"
    r"|quel (?:est|etait) (?:le|ce|votre) message"
    r"|quel message"
    r"|(?:le|ce) message\s*\??"
    r"|(?:je ne vois pas|montre(?:z)?(?: moi)?|affiche(?:z)?) (?:le|ce) message"
    r")\s*[?.!]*$",
    re.IGNORECASE,
)
NO_DETAIL_TEXT = (
    "Je n'ai pas de message en attente pour vous. Écrivez « mes rappels » pour "
    "voir ce qui est programmé."
)


def is_detail_request(text: str) -> bool:
    """True when she asks to see the message a discreet notice announced."""
    from app.services.when_fr import normalize

    return bool(DETAIL_REQUEST_RE.match(normalize(text)))


def is_list_request(text: str) -> bool:
    """True when the short message asks for the list of her reminders."""
    return bool(LIST_REQUEST_RE.match((text or "").strip()))


def extract_cancel_number(text: str) -> int | None:
    """The reminder number in « annule le rappel 2 », or None."""
    match = CANCEL_ONE_RE.search(text or "")
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def fetch_user_reminders(wa_id: str, limit: int = 10) -> list[dict]:
    """The user's open reminders via their pseudo_id; [] when none, None on error."""
    pseudo_id = pseudo_id_for(wa_id)
    response = get_json(
        f"/api/bot/users/{pseudo_id}/reminders", params={"limit": limit}
    )
    if response is None or response.status_code != 200:
        LOGGER.warning("fetch_user_reminders failed: %s", "no response" if response is None else f"HTTP {response.status_code}")
        return None
    try:
        data = unwrap(response.json())
    except ValueError:
        LOGGER.warning("fetch_user_reminders failed: unreadable body")
        return None
    return data if isinstance(data, list) else None


def snapshot(wa_id: str, limit: int = 5) -> list[dict] | None:
    """Her pending reminders for the prompt note, cached for a couple of minutes.

    The note is built on every message that reaches the model, so a burst of
    messages must not mean a backend call each. `None` (unreachable) is never
    cached and never confused with an empty list: the model is told nothing
    rather than told she has no reminder.
    """
    pseudo_id = pseudo_id_for(wa_id)
    cached = reminder_snapshot.get(pseudo_id)
    if isinstance(cached, list):
        return cached
    reminders = fetch_user_reminders(wa_id, limit=limit)
    if reminders is None:
        return None
    reminder_snapshot.set(pseudo_id, reminders)
    return reminders


def forget_snapshot(wa_id: str) -> None:
    """Drops the cached snapshot after a create, a cancel or an opt-out."""
    reminder_snapshot.pop(pseudo_id_for(wa_id))


def cancel_user_reminder(wa_id: str, reminder_id: str) -> dict | None:
    """Cancels one reminder via the backend; the cancelled item on success,
    None on any failure (missing, not yours, already done, unreachable)."""
    if not reminder_id:
        return None
    pseudo_id = pseudo_id_for(wa_id)
    reminder_snapshot.pop(pseudo_id)
    response = post_json(
        f"/api/bot/reminders/{reminder_id}/cancel",
        {},
        params={"pseudo_id": pseudo_id},
    )
    if response is None or response.status_code != 200:
        LOGGER.warning("cancel_user_reminder failed: %s", "no response" if response is None else f"HTTP {response.status_code}")
        return None
    try:
        data = unwrap(response.json())
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _remember_before(list_: list[dict], pseudo_id: str) -> None:
    """Stores the list a user has just seen, so "le rappel 2" resolves to an id.

    The backend returns a fresh snapshot on every call and the cache is
    per-user TTL, so a number map is valid only for the list she was shown.
    What a move needs is kept too, so the reminder can be recreated at another
    date without asking her again.
    """
    last_ids = [
        {
            "id": item.get("id"),
            "kind": item.get("kind"),
            "message": item.get("message"),
            "repeat_interval_days": item.get("repeat_interval_days"),
            "scheduled_at": item.get("scheduled_at"),
        }
        for item in list_
    ]
    reminder_last_list.set(pseudo_id, last_ids)


def reminders_last_shown(wa_id: str) -> list[dict]:
    """The reminders of the list she was shown, in the order she saw them."""
    return reminder_last_list.get(pseudo_id_for(wa_id)) or []


def _cancellable(reminders: list[dict]) -> bool:
    return len(reminders) <= 3


def _as_dict(payload) -> dict:
    return json.loads(payload) if isinstance(payload, str) else payload


def _body_text(payload) -> str:
    data = _as_dict(payload)
    return (
        data.get("text", {}).get("body")
        or data.get("interactive", {}).get("body", {}).get("text", "")
        or ""
    )


def build_list_payload(wa_id: str, reminders: list[dict]) -> dict:
    """The text + optional cancel buttons for the current list."""
    pseudo_id = pseudo_id_for(wa_id)
    _remember_before(reminders, pseudo_id)
    if not reminders:
        return get_text_message_input(wa_id, NO_REMINDERS_TEXT)
    lines = [LIST_HEADER] + [
        _line(item, number) for number, item in enumerate(reminders, start=1)
    ]
    if len(reminders) > 3:
        lines.append(LIST_FOOTER)
    buttons = None
    if _cancellable(reminders):
        buttons = [
            (f"REM:CANCEL:{item.get('id')}", CANCEL_BUTTON_TITLE.format(n=n))
            for n, item in enumerate(reminders, start=1)
        ]
    if buttons:
        return build_buttons_payload(wa_id, "\n".join(lines), buttons)
    return get_text_message_input(wa_id, "\n".join(lines))


def handle_list_request(wa_id: str, send) -> str:
    """Sends the factual list (or an honest unavailable text). Returns the text."""
    reminders = fetch_user_reminders(wa_id)
    if reminders is None:
        text = LIST_UNAVAILABLE_TEXT
        send(get_text_message_input(wa_id, text))
        return text
    payload = build_list_payload(wa_id, reminders)
    send(payload)
    return _body_text(payload)


def handle_cancel_one(wa_id: str, number: int, send) -> str:
    """Cancels the reminder at position `number` of the last shown list."""
    pseudo_id = pseudo_id_for(wa_id)
    last = reminder_last_list.get(pseudo_id) or []
    if not 1 <= number <= len(last):
        text = CANCEL_UNKNOWN_TEXT
        send(get_text_message_input(wa_id, text))
        return text
    cancelled = cancel_user_reminder(wa_id, last[number - 1].get("id"))
    if cancelled is None:
        text = CANCEL_ERROR_TEXT
        send(get_text_message_input(wa_id, text))
        return text
    text = _confirm_cancel(cancelled)
    send(get_text_message_input(wa_id, text))
    return text


def handle_button(wa_id: str, button_id: str, send) -> None:
    """REM:CANCEL:<id> — the cancel button under a listed reminder."""
    if not button_id.startswith("REM:CANCEL:"):
        return
    reminder_id = button_id[len("REM:CANCEL:"):]
    if not reminder_id:
        return
    cancelled = cancel_user_reminder(wa_id, reminder_id)
    if cancelled is None:
        text = CANCEL_ERROR_TEXT
        send(get_text_message_input(wa_id, text))
        return
    text = _confirm_cancel(cancelled)
    send(get_text_message_input(wa_id, text))