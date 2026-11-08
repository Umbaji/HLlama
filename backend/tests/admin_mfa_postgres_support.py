import os
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from models.admin_mfa import (
    AdminMfaChallengeModel,
    AdminMfaCredentialModel,
    AdminMfaRecoveryCodeModel,
)
from models.user import UserModel

MFA_TABLES = (
    UserModel,
    AdminMfaCredentialModel,
    AdminMfaChallengeModel,
    AdminMfaRecoveryCodeModel,
)


@pytest.fixture(scope="module")
def mfa_postgres_sessions() -> Iterator[sessionmaker[Session]]:
    database_url = os.getenv("MFA_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("MFA_TEST_DATABASE_URL is not configured")
    parsed = make_url(database_url)
    if parsed.host not in {"localhost", "127.0.0.1", "::1"}:
        pytest.fail("MFA integration tests require a local PostgreSQL instance")
    if not (parsed.database or "").lower().endswith("_mfa_test"):
        pytest.fail("MFA integration tests require a dedicated *_mfa_test database")
    engine = create_engine(database_url, pool_size=5, max_overflow=0)
    for model in MFA_TABLES:
        model.__table__.create(engine, checkfirst=True)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        for model in reversed(MFA_TABLES):
            model.__table__.drop(engine, checkfirst=True)
        engine.dispose()
