"""Reads the date and time she types, in her own French.

The model returns an ISO value, but when the bot asks the question itself
("à quelle date ?") her answer is plain French and never reached a parser: the
reminder was simply lost. Everything here is pure and takes `now`, so the tests
own the clock.

Naive local date-times throughout: the backend converts them with the timezone
of her number.
"""
import re
import unicodedata
from datetime import date, datetime, timedelta

DEFAULT_HOUR = 8
# The reminder poller runs every 30 seconds and the backend refuses a past
# date: "dans 10s" becomes the first minute it can honestly be sent.
MIN_LEAD = timedelta(minutes=1)

_WEEKDAYS = {
    "lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3,
    "vendredi": 4, "samedi": 5, "dimanche": 6,
}
_UNITS = {
    "s": timedelta(seconds=1), "sec": timedelta(seconds=1),
    "secs": timedelta(seconds=1), "seconde": timedelta(seconds=1),
    "secondes": timedelta(seconds=1),
    "min": timedelta(minutes=1), "mins": timedelta(minutes=1),
    "mn": timedelta(minutes=1), "minute": timedelta(minutes=1),
    "minutes": timedelta(minutes=1),
    "h": timedelta(hours=1), "heure": timedelta(hours=1), "heures": timedelta(hours=1),
    "j": timedelta(days=1), "jour": timedelta(days=1), "jours": timedelta(days=1),
    "semaine": timedelta(weeks=1), "semaines": timedelta(weeks=1),
    "mois": timedelta(days=30),
}
# "dans une minute", "dans deux jours": she spells small numbers out.
_SPELLED = {
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
    "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10,
}

_TIME_RE = re.compile(r"\b(\d{1,2})\s*(?:h|:)\s*(\d{2})?\b")
_DAY_MONTH_RE = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})(?:[/\-.](\d{2,4}))?\b")
_COUNT = r"(\d{1,3}|" + "|".join(_SPELLED) + r")\s*"
_IN_RE = re.compile(
    r"\b(?:dans|d ici)\s+" + _COUNT
    + r"(secondes?|secs?|minutes?|mins?|heures?|jours?|semaines?|mois|s|mn|h|j)\b"
)
# "a 2s", "a 10 min": the same delay said with "à". Only the short units, so
# "à 20h" stays the hour she means and never becomes twenty hours from now.
_IN_SHORT_RE = re.compile(r"\ba\s+" + _COUNT + r"(secondes?|secs?|minutes?|mins?|s|mn)\b")


def normalize(value: str) -> str:
    """Lowercase, accent-free, single-spaced, apostrophes as spaces.

    The hyphen is kept: it separates "apres-demain" but also "25-10".
    """
    decomposed = unicodedata.normalize("NFKD", value or "")
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"['’]", " ", stripped.lower())).strip()


def _iso(text: str) -> datetime | None:
    candidate = text.strip().replace(" ", "T", 1) if " " in text.strip() else text.strip()
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed


def _time_in(text: str) -> tuple[int, int] | None:
    match = _TIME_RE.search(text)
    if match:
        hour, minute = int(match.group(1)), int(match.group(2) or 0)
        return (hour, minute) if hour < 24 and minute < 60 else None
    # "a 8" alone stays ambiguous; only "8h" or "8:30" count as a time.
    return None


def _at(day: date, clock: tuple[int, int] | None) -> datetime:
    hour, minute = clock or (DEFAULT_HOUR, 0)
    return datetime(day.year, day.month, day.day, hour, minute)


def _day_month(text: str, now: datetime, clock: tuple[int, int] | None) -> datetime | None:
    match = _DAY_MONTH_RE.search(text)
    if not match:
        return None
    day, month = int(match.group(1)), int(match.group(2))
    raw_year = match.group(3)
    year = now.year if raw_year is None else int(raw_year) + (2000 if len(raw_year) == 2 else 0)
    try:
        moment = _at(date(year, month, day), clock)
    except ValueError:
        return None
    # "25/12" written in January means this year; written in December, next year.
    if raw_year is None and moment <= now:
        try:
            moment = moment.replace(year=year + 1)
        except ValueError:
            return None
    return moment


def _relative_day(text: str, now: datetime, clock: tuple[int, int] | None) -> datetime | None:
    if "apres demain" in text or "apres-demain" in text:
        return _at(now.date() + timedelta(days=2), clock)
    if "demain" in text:
        return _at(now.date() + timedelta(days=1), clock)
    if "aujourd hui" in text or "ce soir" in text or "tout a l heure" in text:
        return _at(now.date(), clock)
    return None


def _weekday(text: str, now: datetime, clock: tuple[int, int] | None) -> datetime | None:
    for name, index in _WEEKDAYS.items():
        if re.search(rf"\b{name}\b", text):
            ahead = (index - now.weekday()) % 7
            if ahead == 0:
                ahead = 7
            moment = _at(now.date() + timedelta(days=ahead), clock)
            if "prochain" in text and ahead < 7:
                moment += timedelta(days=7)
            return moment
    return None


def parse_when(text: str, now: datetime) -> datetime | None:
    """Her date and time as a naive local datetime, or None when unreadable.

    Only a future moment is returned: a date already gone is a question to ask
    again, never a reminder that fires immediately.
    """
    raw = (text or "").strip()
    if not raw:
        return None

    moment = _iso(raw)
    if moment is None:
        normalized = normalize(raw)
        clock = _time_in(normalized)
        match = _IN_RE.search(normalized) or _IN_SHORT_RE.search(normalized)
        if match:
            count = match.group(1)
            moment = now + (int(count) if count.isdigit() else _SPELLED[count]) * _UNITS[match.group(2)]
        else:
            moment = (
                _day_month(normalized, now, clock)
                or _relative_day(normalized, now, clock)
                or _weekday(normalized, now, clock)
            )
        if moment is None and clock is not None:
            # A bare "20h": today while it is still ahead, tomorrow otherwise.
            moment = _at(now.date(), clock)
            if moment <= now:
                moment += timedelta(days=1)

    if moment is None or moment <= now:
        return None
    # "dans 10 secondes" can only be honest as the next minute: the poller has
    # a 30s period and the backend refuses a date already gone.
    if moment - now < MIN_LEAD:
        moment = now + MIN_LEAD
    return moment.replace(second=0, microsecond=0)
