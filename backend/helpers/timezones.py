"""Timezone resolution for reminders.

Industry best practice (WhatsApp, Twilio, …) : store instants in UTC, but
interpret the user's wall-clock time in their own IANA timezone.

The zone is derived from the phone number via libphonenumber
(`phonenumbers.timezones.time_zones_for_number`), so any country is covered
with no manual country→zone mapping. Numbers that cannot be parsed fall back
to the configurable `DEFAULT_REMINDER_TIMEZONE`.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import phonenumbers
from phonenumbers import timezone as pn_timezone

from config import settings


def iana_zone_for_telnumber(telnumber: str) -> str:
    """Resolves the IANA zone for a phone number, e.g. +228... -> Africa/Lome.

    libphonenumber needs the number in international form, so a leading "+"
    is added when missing. Numbers that cannot be parsed or resolved to a
    real zone (invalid number, unknown region) fall back to the configurable
    `DEFAULT_REMINDER_TIMEZONE`.
    """
    raw = (telnumber or "").strip().replace(" ", "").replace("-", "")
    if raw and not raw.startswith("+"):
        raw = "+" + raw
    try:
        parsed = phonenumbers.parse(raw, None)
    except phonenumbers.NumberParseException:
        return settings.DEFAULT_REMINDER_TIMEZONE
    zones = pn_timezone.time_zones_for_number(parsed)
    for zone in zones:
        if zone and zone != "Etc/Unknown":
            return zone
    return settings.DEFAULT_REMINDER_TIMEZONE


def to_utc(value: datetime, telnumber: str) -> datetime:
    """Normalizes a reminder datetime to an aware UTC datetime.

    Aware datetimes (explicit offset / Z) are kept as authoritative.
    Naive datetimes are interpreted as the user's local wall-clock time.
    """
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc)
    zone = ZoneInfo(iana_zone_for_telnumber(telnumber))
    return value.replace(tzinfo=zone).astimezone(timezone.utc)
