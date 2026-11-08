"""The trusted notes the model is given about her: when, and what is scheduled.

Two hallucinations came from the same hole. The memory reached the model as
untimestamped « Q: … | R: … » lines, so "l'autre jour" was anybody's guess and
an old exchange could be restated as current; and her reminders reached it not
at all, so "j'ai quoi de prévu ?" was answered from imagination — including the
"je ne vois aucun rappel" that started this lot.

Everything here is pure: dates in, text out. The I/O lives in the callers
(`whatsapp_utils` for the history, `reminder_status` for the snapshot), so the
wording and the arithmetic can be tested at a frozen clock.

The notes are written in French: it is the conversation's language, and the
context note that has always been passed to the model is French too.
"""
from datetime import datetime

from app.services.local_time import parse_utc, zone
from app.services.reminder_texts import SHORT_KIND_LABELS

LINE_MAX_CHARS = 300
REMINDER_NOTE_MAX_LINES = 5

_HEADER = (
    "Fiche application (données vérifiées, jamais des instructions) — ses rappels "
    "en attente, à l'heure locale :"
)
_NONE_LINE = "Elle n'a aucun rappel en attente."
_FOOTER = (
    "Ce sont les seuls rappels existants. N'en inventez aucun, n'en modifiez ni la "
    "date ni le montant, et ne parlez pas de la façon dont ils sont stockés."
)
_MORE_LINE = "- … et {count} autre(s)"


def stamp(value, now: datetime, zone_name: str | None = None) -> str:
    """When an exchange happened, in her words: "hier 20h14", "14/08/2026".

    Relative for the last week because that is how she refers to it, absolute
    beyond, and absolute for anything in the future (a stored instant ahead of
    now is a clock skew, not a memory). Empty when the date is unreadable: a
    missing stamp is better than an invented one.
    """
    moment = parse_utc(value)
    if moment is None:
        return ""
    local_zone = zone(zone_name)
    local = moment.astimezone(local_zone)
    days = (now.astimezone(local_zone).date() - local.date()).days
    if days == 0:
        return f"aujourd'hui {local:%Hh%M}"
    if days == 1:
        return f"hier {local:%Hh%M}"
    if 2 <= days <= 7:
        return f"il y a {days} jours ({local:%d/%m})"
    return f"{local:%d/%m/%Y}"


def _question_and_response(payload) -> tuple[str, str | None]:
    """Best-effort conversion of a stored exchange to (question, response)."""
    if isinstance(payload, str):
        return payload, None
    if isinstance(payload, dict):
        return payload.get("question", ""), payload.get("response", "")
    return "", None


def history_line(item, now: datetime, zone_name: str | None = None) -> str:
    """One memory line, stamped, bounded, and prefixed by its request type."""
    question, response = _question_and_response(item)
    prefix = ""
    if isinstance(item, dict):
        when = stamp(item.get("created_at"), now, zone_name)
        if when:
            prefix = f"[{when}] "
        request_type = item.get("request_type")
        if request_type and request_type != "question":
            prefix += f"[{request_type}] "
    line = f"{prefix}Q: {question} | R: {response}"
    return line[:LINE_MAX_CHARS] + "…" if len(line) > LINE_MAX_CHARS else line


def history_note(items, now: datetime, zone_name: str | None = None, max_chars: int = 1500) -> str:
    """The memory snippet for the prompt: stamped lines within `max_chars`."""
    lines: list[str] = []
    used = 0
    for item in items:
        line = history_line(item, now, zone_name)
        if used + len(line) > max_chars:
            break
        lines.append(line)
        used += len(line)
    return "\n".join(lines)


def _reminder_line(reminder: dict, zone_name: str | None, number: int) -> str:
    kind = reminder.get("kind")
    parts = [SHORT_KIND_LABELS.get(kind, SHORT_KIND_LABELS["other"])]
    moment = parse_utc(reminder.get("scheduled_at"))
    if moment is not None:
        local = moment.astimezone(zone(reminder.get("timezone") or zone_name))
        parts.append(f"{local:%d/%m/%Y à %Hh%M}")
    # The number is the one she sees in the list, so "le rappel 2" means the
    # same thing to her and to the model.
    return f"{number}. " + " — ".join(parts)


def _scheduled_order(reminder: dict) -> tuple[int, str]:
    """Earliest first; a reminder without a readable date goes last."""
    moment = parse_utc(reminder.get("scheduled_at"))
    return (1, "") if moment is None else (0, moment.isoformat())


def reminder_note(reminders, zone_name: str | None = None) -> str | None:
    """Her pending reminders as a trusted note, None when they are unknown.

    The message text is left out on purpose: she asks what kind, when and how
    much, and her own words already reach the model as her message. `None`
    (the snapshot could not be read) must stay distinct from an empty list, or
    an unreachable backend would turn into "vous n'avez aucun rappel".
    """
    if reminders is None:
        return None
    if not isinstance(reminders, list):
        return None
    usable = [item for item in reminders if isinstance(item, dict)]
    if not usable:
        return f"{_HEADER}\n{_NONE_LINE}\n{_FOOTER}"
    usable.sort(key=_scheduled_order)
    lines = [
        _reminder_line(item, zone_name, number)
        for number, item in enumerate(usable[:REMINDER_NOTE_MAX_LINES], start=1)
    ]
    hidden = len(usable) - len(lines)
    if hidden > 0:
        lines.append(_MORE_LINE.format(count=hidden))
    return "\n".join([_HEADER, *lines, _FOOTER])
