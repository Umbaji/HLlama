"""Her local wall-clock time, derived from her WhatsApp number.

Mirrors the backend's helpers/timezones.py so a naive local date-time sent to
the backend is read back as the same wall-clock moment. Lives in services, not
in whatsapp_utils, so anything that needs "now, where she is" can import it
without pulling torch in.
"""
import os
from datetime import datetime, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_ZONE_ENV = "DEFAULT_REMINDER_TIMEZONE"
FALLBACK_ZONE = "Africa/Lome"


def zone(name: str | None = None) -> tzinfo:
    """`name` as a timezone, else the configured default, else UTC."""
    for candidate in (name, os.getenv(DEFAULT_ZONE_ENV), FALLBACK_ZONE):
        if not candidate:
            continue
        try:
            return ZoneInfo(candidate)
        except (ZoneInfoNotFoundError, ValueError):
            continue
    return timezone.utc


def parse_utc(value) -> datetime | None:
    """An ISO instant from the backend as an aware date-time, None when unreadable.

    The backend stores UTC; a value that comes back without an offset is UTC
    without its offset, never local time.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def zone_name_for_wa_id(wa_id: str) -> str:
    """The IANA timezone of her number, or the configured default."""
    default_zone = os.getenv(DEFAULT_ZONE_ENV, FALLBACK_ZONE)
    raw = (wa_id or "").strip().replace(" ", "").replace("-", "")
    if not raw:
        return default_zone
    if not raw.startswith("+"):
        raw = "+" + raw
    try:
        import phonenumbers
        from phonenumbers import timezone as pn_timezone

        parsed = phonenumbers.parse(raw, None)
        for zone in pn_timezone.time_zones_for_number(parsed):
            if zone and zone != "Etc/Unknown":
                return zone
    except Exception:
        pass
    return default_zone


def now_local(wa_id: str = "") -> datetime:
    """Naive local date-time where she is, for parsing and for comparisons."""
    return datetime.now(zone(zone_name_for_wa_id(wa_id))).replace(tzinfo=None)
