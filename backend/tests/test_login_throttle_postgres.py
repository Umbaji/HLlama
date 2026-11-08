import os
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from fastapi import Request
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session, sessionmaker

from models.login_attempt import LoginAttemptBucketModel
from services.login_throttle import reserve_login_attempt

POSTGRES_URL = os.getenv("LOGIN_THROTTLE_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="PostgreSQL login-throttle integration database is not configured",
)


@pytest.fixture()
def sessions() -> Generator[sessionmaker[Session], None, None]:
    assert POSTGRES_URL is not None
    engine = create_engine(POSTGRES_URL, pool_size=20, max_overflow=0)
    LoginAttemptBucketModel.__table__.create(engine, checkfirst=True)
    factory = sessionmaker(bind=engine)
    with factory.begin() as session:
        session.execute(delete(LoginAttemptBucketModel))
    try:
        yield factory
    finally:
        with factory.begin() as session:
            session.execute(delete(LoginAttemptBucketModel))
        LoginAttemptBucketModel.__table__.drop(engine, checkfirst=True)
        engine.dispose()


def _reserve(factory: sessionmaker[Session], username: str):
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/login",
            "headers": [],
            "client": ("192.0.2.25", 1234),
            "server": ("localhost", 80),
            "scheme": "http",
            "query_string": b"",
        }
    )
    with factory() as session:
        return reserve_login_attempt(session, request, username)


def test_parallel_requests_share_atomic_identity_budget(
    sessions: sessionmaker[Session],
) -> None:
    with ThreadPoolExecutor(max_workers=20) as workers:
        reservations = list(
            workers.map(
                lambda _index: _reserve(sessions, "parallel@example.com"),
                range(20),
            )
        )

    assert sum(item.identity_blocked_until is None for item in reservations) == 5
    with sessions() as session:
        identity = session.execute(
            select(LoginAttemptBucketModel).where(
                LoginAttemptBucketModel.bucket_kind == "identity"
            )
        ).scalar_one()
        assert identity.attempt_count == 5
        assert identity.blocked_until is not None
        assert identity.expires_at > datetime.now(timezone.utc)
