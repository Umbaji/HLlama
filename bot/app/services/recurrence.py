"""How often a reminder comes back.

The backend repeats a reminder on a fixed number of days, which covers "every
day" and "every week". "Every month" is not a fixed number of days: the 31st is
missing from four months of the year, and thirty days lands on a different day
every time. So a monthly reminder is a set of dated reminders, one per month,
and the bot creates them itself.
"""
import calendar
from datetime import datetime

DAILY = "daily"
WEEKLY = "weekly"
MONTHLY = "monthly"

PATTERNS = (DAILY, WEEKLY, MONTHLY)

# The intervals the backend can repeat on its own.
INTERVAL_DAYS = {DAILY: 1, WEEKLY: 7}

# Six occurrences is half a year: long enough to be useful, short enough that
# she can see them all in her list and cancel the ones she does not want.
MONTHLY_OCCURRENCES = 6


def interval_days(pattern: str | None) -> int | None:
    """The backend interval for a pattern, None when the pattern is monthly."""
    return INTERVAL_DAYS.get(pattern or "")


def monthly_dates(first: datetime, count: int = MONTHLY_OCCURRENCES) -> list[datetime]:
    """The same day each month, on the last day of the month when it is shorter.

    A reminder on the 31st falls on 31 January, then 28 or 29 February, then
    31 March: skipping the short months would skip a dose, which is worse than
    moving it a day or two.
    """
    dates: list[datetime] = []
    year, month = first.year, first.month
    for _ in range(count):
        last_day = calendar.monthrange(year, month)[1]
        dates.append(first.replace(year=year, month=month, day=min(first.day, last_day)))
        month += 1
        if month > 12:
            month = 1
            year += 1
    return dates


def occurrences(first: datetime, pattern: str | None, interval: int | None = None) -> list[datetime]:
    """The dates a reminder comes back on.

    A monthly reminder is a list of dates the bot creates one by one; the other
    patterns are a single reminder the backend repeats.
    """
    if pattern == MONTHLY:
        return monthly_dates(first)
    return [first]
