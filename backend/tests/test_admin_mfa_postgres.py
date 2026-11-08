import hashlib
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from helpers.server_message import ServerMessageException
from models.admin_mfa import (
    AdminMfaCredentialModel,
    AdminMfaRecoveryCodeModel,
)
from models.user import UserModel
from services.admin_mfa import consume_challenge, create_challenge, get_challenge
from services.admin_mfa_access import claim_totp_counter
from admin_mfa_postgres_support import mfa_postgres_sessions


def _user(db: Session) -> UserModel:
    suffix = uuid.uuid4().hex
    user = UserModel(
        pseudo_id=suffix,
        email=f"{suffix}@mfa-test.invalid",
        password_hash="not-used",
        is_admin=True,
        is_active=True,
    )
    db.add(user)
    db.commit()
    return user


def _parallel(call: Callable[[], bool]) -> list[bool]:
    gate = threading.Barrier(2)

    def run():
        gate.wait()
        return call()

    with ThreadPoolExecutor(max_workers=2) as pool:
        return list(pool.map(lambda _index: run(), range(2)))


def test_challenge_is_consumed_once_across_sessions(
    mfa_postgres_sessions: sessionmaker[Session],
) -> None:
    with mfa_postgres_sessions() as db:
        user = _user(db)
        token = create_challenge(db, user.id, "verify")
        db.commit()

    def consume() -> bool:
        with mfa_postgres_sessions() as db:
            try:
                challenge = get_challenge(db, token, "verify")
                consume_challenge(challenge)
                db.commit()
                return True
            except ServerMessageException:
                db.rollback()
                return False

    assert sorted(_parallel(consume)) == [False, True]


def test_totp_counter_update_is_atomic_across_sessions(
    mfa_postgres_sessions: sessionmaker[Session],
) -> None:
    with mfa_postgres_sessions() as db:
        user = _user(db)
        db.add(
            AdminMfaCredentialModel(
                user_id=user.id,
                encrypted_secret="encrypted",
                key_version=1,
                last_totp_counter=100,
                enabled_at=datetime.now(timezone.utc),
                created_at=datetime.now(timezone.utc),
            )
        )
        db.commit()

    def claim() -> bool:
        with mfa_postgres_sessions() as db:
            result = claim_totp_counter(db, user.id, 101)
            db.commit()
            return result

    assert sorted(_parallel(claim)) == [False, True]


def test_recovery_code_is_consumed_once_across_sessions(
    mfa_postgres_sessions: sessionmaker[Session],
) -> None:
    with mfa_postgres_sessions() as db:
        user = _user(db)
        digest = hashlib.sha256(b"recovery-code").hexdigest()
        db.add(
            AdminMfaRecoveryCodeModel(
                id=uuid.uuid4(),
                user_id=user.id,
                code_digest=digest,
                created_at=datetime.now(timezone.utc),
            )
        )
        db.commit()

    def consume() -> bool:
        with mfa_postgres_sessions() as db:
            code = db.execute(
                select(AdminMfaRecoveryCodeModel)
                .where(
                    AdminMfaRecoveryCodeModel.user_id == user.id,
                    AdminMfaRecoveryCodeModel.code_digest == digest,
                    AdminMfaRecoveryCodeModel.consumed_at.is_(None),
                )
                .with_for_update()
            ).scalar_one_or_none()
            if code is None:
                db.rollback()
                return False
            code.consumed_at = datetime.now(timezone.utc)
            db.commit()
            return True

    assert sorted(_parallel(consume)) == [False, True]
