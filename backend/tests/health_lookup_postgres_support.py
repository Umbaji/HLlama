import os
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from models.health_lookup_bucket import HealthLookupBucketModel


@pytest.fixture(scope="module")
def health_postgres_sessions() -> Iterator[sessionmaker[Session]]:
    database_url = os.getenv("HEALTH_LOOKUP_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("HEALTH_LOOKUP_TEST_DATABASE_URL is not configured")
    parsed = make_url(database_url)
    if parsed.host not in {"localhost", "127.0.0.1", "::1"}:
        pytest.fail("health lookup tests require a local PostgreSQL instance")
    if not (parsed.database or "").lower().endswith("_health_test"):
        pytest.fail("health lookup tests require a dedicated *_health_test database")
    engine = create_engine(database_url, pool_size=12, max_overflow=0)
    HealthLookupBucketModel.__table__.create(engine, checkfirst=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        HealthLookupBucketModel.__table__.drop(engine, checkfirst=True)
        engine.dispose()
