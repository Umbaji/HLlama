import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from helpers.server_message import ServerMessageException, typed_server_message
from models.admin_mfa import AdminMfaCredentialModel, AdminMfaRecoveryCodeModel
from models.user import UserModel
from schemas.auth import MfaRecoverRequest, MfaVerifyRequest
from schemas.common import ResponseMetadata, ServerMessage, SuccessEnvelope
from schemas.auth import Token
from services.admin_mfa import (
    consume_challenge,
    decrypt_secret,
    recovery_digest,
)
from services.admin_mfa_access import (
    access_token,
    active_admin,
    check_challenge_limit,
    claim_totp_counter,
    load_challenge,
    reserve_challenge_attempt,
    valid_totp_counter,
)
from services.login_throttle import clear_identity_bucket

router = APIRouter(prefix="/api/login/mfa", tags=["auth"])
logger = logging.getLogger(__name__)


def _verified_user(
    body: MfaVerifyRequest, request: Request, db: Session
) -> UserModel:
    reservation = reserve_challenge_attempt(db, request, body.challenge_token)
    challenge = load_challenge(db, body.challenge_token, "verify", reservation)
    user = active_admin(db, challenge.user_id, reservation)
    credential = db.get(AdminMfaCredentialModel, user.id)
    if credential is None or credential.enabled_at is None:
        check_challenge_limit(reservation)
        raise ServerMessageException("MFA_INVALID", status=401)
    counter = valid_totp_counter(
        decrypt_secret(credential.encrypted_secret, user.id), body.code
    )
    if counter is None or not claim_totp_counter(db, user.id, counter):
        db.rollback()
        check_challenge_limit(reservation)
        raise ServerMessageException("MFA_INVALID", status=401)
    consume_challenge(challenge)
    clear_identity_bucket(db, reservation.identity_key)
    return user


@router.post(
    "/verify",
    response_model=SuccessEnvelope[Token, ResponseMetadata],
    responses={
        401: {"model": ServerMessage},
        503: {"model": ServerMessage},
    },
)
def verify_mfa(
    body: MfaVerifyRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    user = _verified_user(body, request, db)
    db.commit()
    return typed_server_message(
        "LOGIN_SUCCESS",
        access_token(user),
        SuccessEnvelope[Token, ResponseMetadata],
        "auth_mfa_verify",
        headers={"Cache-Control": "no-store"},
    )


@router.post(
    "/recover",
    response_model=SuccessEnvelope[Token, ResponseMetadata],
    responses={
        401: {"model": ServerMessage},
        503: {"model": ServerMessage},
    },
)
def recover_mfa(
    body: MfaRecoverRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    reservation = reserve_challenge_attempt(db, request, body.challenge_token)
    challenge = load_challenge(db, body.challenge_token, "verify", reservation)
    user = active_admin(db, challenge.user_id, reservation)
    digest = recovery_digest(body.recovery_code)
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
        check_challenge_limit(reservation)
        raise ServerMessageException("MFA_RECOVERY_CODE_INVALID", status=401)
    now = datetime.now(timezone.utc)
    code.consumed_at = now
    consume_challenge(challenge, now)
    clear_identity_bucket(db, reservation.identity_key)
    logger.info("admin_mfa_recovery_used")
    db.commit()
    return typed_server_message(
        "LOGIN_SUCCESS",
        access_token(user),
        SuccessEnvelope[Token, ResponseMetadata],
        "auth_mfa_recover",
        headers={"Cache-Control": "no-store"},
    )
