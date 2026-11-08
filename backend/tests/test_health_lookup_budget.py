from datetime import datetime, timezone

from sqlalchemy.orm import Session

from services.health_lookup_limit import reserve_health_lookup

pytest_plugins = ("health_lookup_test_support",)

BOT_KEY = "health-test-bot-key"


def test_fixed_window_resets_at_boundary(db: Session) -> None:
    first = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)
    assert reserve_health_lookup(db, BOT_KEY, "geocode", 1, first) == 0
    assert reserve_health_lookup(
        db, BOT_KEY, "geocode", 1, first.replace(minute=1)
    ) == 0
