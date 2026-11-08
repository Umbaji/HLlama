import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Request
from sqlalchemy import or_, update
from sqlalchemy.orm import Session

from helpers.server_message import ServerMessageException
from models.admin_mfa import AdminMfaChallengeModel, AdminMfaCredentialModel
from models.user import UserModel
from schemas.auth import Token
from services.admin_mfa import get_challenge, matching_totp_counter
from services.auth_service import ACCESS_TOKEN_EXPIRE_MINUTES, create_access_token
from services.login_throttle import (
    LoginReservation,
    raise_login_limited,
    reserve_login_attempt,
)


def reserve_challenge_attempt(
    db: Session, request: Request, token: str
) -> LoginReservation:
    digest = hashlib.sha256(token.encode()).hexdigest()
    return reserve_login_attempt(db, request, f"{digest[:32]}@mfa.invalid")


def check_challenge_limit(reservation: LoginReservation) -> None:
    blocked_until = reservation.identity_blocked_until
    if blocked_until:
        raise_login_limited(blocked_until, datetime.now(timezone.utc))


def load_challenge(
    db: Session,
    token: str,
    purpose: str,
    reservation: LoginReservation,
) -> AdminMfaChallengeModel:
    try:
        return get_challenge(db, token, purpose)
    except ServerMessageException:
        db.rollback()
        check_challenge_limit(reservation)
        raise


def active_admin(
    db: Session, user_id: uuid.UUID, reservation: LoginReservation
) -> UserModel:
    user = db.get(UserModel, user_id)
    if user is None or not user.is_active or not user.is_admin:
        check_challenge_limit(reservation)
        raise ServerMessageException("MFA_INVALID", status=401)
    return user


def access_token(user: UserModel) -> Token:
    token = create_access_token(
        {"sub": user.email, "mfa": True},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return Token(access_token=token, token_type="bearer")


def claim_totp_counter(
    db: Session,
    user_id: uuid.UUID,
    counter: int,
    enabled_at: datetime | None = None,
) -> bool:
    statement = (
        update(AdminMfaCredentialModel)
        .where(
            AdminMfaCredentialModel.user_id == user_id,
            or_(
                AdminMfaCredentialModel.last_totp_counter.is_(None),
                AdminMfaCredentialModel.last_totp_counter < counter,
            ),
        )
        .values(last_totp_counter=counter)
        .execution_options(synchronize_session=False)
    )
    if enabled_at is not None:
        statement = statement.where(AdminMfaCredentialModel.enabled_at.is_(None)).values(
            enabled_at=enabled_at
        )
    else:
        statement = statement.where(AdminMfaCredentialModel.enabled_at.is_not(None))
    return db.execute(statement).rowcount == 1


def valid_totp_counter(secret: str, code: str) -> int | None:
    return matching_totp_counter(secret, code)
