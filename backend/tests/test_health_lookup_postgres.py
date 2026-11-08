from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from sqlalchemy.orm import Session, sessionmaker

from services.health_lookup_limit import reserve_health_lookup

pytest_plugins = ("health_lookup_postgres_support",)


def test_concurrent_lookups_never_exceed_the_shared_budget(
    health_postgres_sessions: sessionmaker[Session],
) -> None:
    now = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)

    def reserve(_: int) -> int:
        with health_postgres_sessions() as db:
            return reserve_health_lookup(
                db, "parallel-test-credential", "nearest", 5, now
            )

    with ThreadPoolExecutor(max_workers=12) as executor:
        outcomes = list(executor.map(reserve, range(12)))

    assert outcomes.count(0) == 5
    assert all(1 <= retry_ms <= 60_000 for retry_ms in outcomes if retry_ms)


def test_operations_have_independent_postgres_budgets(
    health_postgres_sessions: sessionmaker[Session],
) -> None:
    now = datetime(2026, 11, 7, 12, 0, tzinfo=timezone.utc)
    with health_postgres_sessions() as db:
        nearest = reserve_health_lookup(db, "same-credential", "nearest", 1, now)
    with health_postgres_sessions() as db:
        geocode = reserve_health_lookup(db, "same-credential", "geocode", 1, now)

    assert nearest == 0
    assert geocode == 0
