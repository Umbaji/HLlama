"""The trusted note the model is given about her history: when each exchange
happened.

The memory reached the model as untimestamped « Q: … | R: … » lines, so
"l'autre jour" was anybody's guess and an old exchange could be restated as
current.

Everything here is pure: dates in, text out. The I/O lives in the caller
(`whatsapp_utils` for the history), so the wording and the arithmetic can be
tested at a frozen clock.

The notes are written in French: it is the conversation's language, and the
context note that has always been passed to the model is French too.
"""
from datetime import datetime

from app.services.local_time import parse_utc, zone

LINE_MAX_CHARS = 300


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

