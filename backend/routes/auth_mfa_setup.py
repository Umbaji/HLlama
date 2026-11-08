import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from helpers.server_message import ServerMessageException, typed_server_message
from models.admin_mfa import AdminMfaCredentialModel, AdminMfaRecoveryCodeModel
from schemas.auth import (
    MfaEnrolled,
    MfaEnrollRequest,
    MfaSetupReady,
    MfaSetupRequest,
)
from schemas.common import ResponseMetadata, ServerMessage, SuccessEnvelope
from services.admin_mfa import (
    consume_challenge,
    create_challenge,
    create_totp_secret,
    decrypt_secret,
    encrypt_secret,
    otp_uri,
    recovery_codes,
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


@router.post(
    "/setup",
    response_model=SuccessEnvelope[MfaSetupReady, ResponseMetadata],
    responses={
        401: {"model": ServerMessage},
        503: {"model": ServerMessage},
    },
)
def setup_mfa(
    body: MfaSetupRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    if not settings.ADMIN_MFA_ENROLLMENT_ENABLED:
        raise ServerMessageException("MFA_UNAVAILABLE", status=503)
    reservation = reserve_challenge_attempt(db, request, body.setup_challenge_token)
    challenge = load_challenge(db, body.setup_challenge_token, "setup", reservation)
    user = active_admin(db, challenge.user_id, reservation)
    if db.get(AdminMfaCredentialModel, user.id) is not None:
        check_challenge_limit(reservation)
        raise ServerMessageException("MFA_INVALID", status=401)
    secret = create_totp_secret()
    db.add(
        AdminMfaCredentialModel(
            user_id=user.id,
            encrypted_secret=encrypt_secret(secret, user.id),
            key_version=1,
            created_at=datetime.now(timezone.utc),
        )
    )
    consume_challenge(challenge)
    enrollment_token = create_challenge(db, user.id, "enroll")
    clear_identity_bucket(db, reservation.identity_key)
    return typed_server_message(
        "MFA_SETUP_READY",
        MfaSetupReady(
            secret=secret,
            otpauth_uri=otp_uri(secret, user.email),
            enroll_challenge_token=enrollment_token,
            expires_in_seconds=300,
        ),
        SuccessEnvelope[MfaSetupReady, ResponseMetadata],
        "auth_mfa_setup",
        headers={"Cache-Control": "no-store"},
    )


@router.post(
    "/enroll",
    response_model=SuccessEnvelope[MfaEnrolled, ResponseMetadata],
    responses={
        401: {"model": ServerMessage},
        503: {"model": ServerMessage},
    },
)
def enroll_mfa(
    body: MfaEnrollRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    reservation = reserve_challenge_attempt(db, request, body.enroll_challenge_token)
    challenge = load_challenge(db, body.enroll_challenge_token, "enroll", reservation)
    user = active_admin(db, challenge.user_id, reservation)
    credential = db.get(AdminMfaCredentialModel, user.id)
    if credential is None or credential.enabled_at is not None:
        check_challenge_limit(reservation)
        raise ServerMessageException("MFA_INVALID", status=401)
    counter = valid_totp_counter(
        decrypt_secret(credential.encrypted_secret, user.id), body.code
    )
    if counter is None:
        db.rollback()
        check_challenge_limit(reservation)
        raise ServerMessageException("MFA_INVALID", status=401)
    now = datetime.now(timezone.utc)
    if not claim_totp_counter(db, user.id, counter, now):
        db.rollback()
        check_challenge_limit(reservation)
        raise ServerMessageException("MFA_INVALID", status=401)
    consume_challenge(challenge, now)
    codes = recovery_codes()
    for code in codes:
        db.add(
            AdminMfaRecoveryCodeModel(
                id=uuid.uuid4(),
                user_id=user.id,
                code_digest=recovery_digest(code),
                created_at=now,
            )
        )
    clear_identity_bucket(db, reservation.identity_key)
    logger.info("admin_mfa_enrolled")
    return typed_server_message(
        "MFA_ENROLLED",
        MfaEnrolled(
            access_token=access_token(user).access_token,
            token_type="bearer",
            recovery_codes=codes,
        ),
        SuccessEnvelope[MfaEnrolled, ResponseMetadata],
        "auth_mfa_enroll",
        headers={"Cache-Control": "no-store"},
    )
