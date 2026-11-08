from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from database import get_db
from helpers.server_message import ServerMessageException, typed_server_message
from schemas.common import ResponseMetadata, ServerMessage, SuccessEnvelope
from schemas.auth import LoginRequest, MfaRequired, MfaSetupRequired, Token
from services.auth_service import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    authenticate_user,
    create_access_token,
)
from services.admin_mfa import create_challenge, encryption_key
from services.login_throttle import (
    clear_identity_bucket,
    raise_login_limited,
    reserve_login_attempt,
)
from config import settings
from models.admin_mfa import AdminMfaCredentialModel

router = APIRouter(prefix="/api", tags=["auth"])
type LoginResponse = Token | MfaRequired | MfaSetupRequired


@router.post(
    "/login",
    response_model=SuccessEnvelope[LoginResponse, ResponseMetadata],
    responses={
        429: {
            "model": ServerMessage,
            "description": "Login attempts temporarily limited.",
        },
        503: {
            "model": ServerMessage,
            "description": "Login protection is unavailable.",
        },
    },
)
def login(
    form_data: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    reservation = reserve_login_attempt(db, request, form_data.username)
    user = authenticate_user(db, form_data.username, form_data.password)
    if reservation.identity_blocked_until and not (user and user.is_active):
        raise_login_limited(
            reservation.identity_blocked_until,
            datetime.now(timezone.utc),
        )
    if not user or not user.is_active:
        raise ServerMessageException(
            "INVALID_CREDENTIALS",
            headers={"WWW-Authenticate": "Bearer"},
        )
    clear_identity_bucket(db, reservation.identity_key)
    if user.is_admin:
        credential = db.get(AdminMfaCredentialModel, user.id)
        if credential is not None and credential.enabled_at is not None:
            token = create_challenge(db, user.id, "verify")
            db.commit()
            return typed_server_message(
                "MFA_REQUIRED",
                MfaRequired(challenge_token=token, expires_in_seconds=300),
                SuccessEnvelope[LoginResponse, ResponseMetadata],
                "auth_login",
                headers={"Cache-Control": "no-store"},
            )
        if settings.ADMIN_MFA_ENROLLMENT_ENABLED or settings.ADMIN_MFA_REQUIRED:
            if credential is not None:
                raise ServerMessageException("MFA_UNAVAILABLE", status=503)
            if not settings.ADMIN_MFA_ENROLLMENT_ENABLED:
                raise ServerMessageException("MFA_UNAVAILABLE", status=503)
            encryption_key()
            token = create_challenge(db, user.id, "setup")
            db.commit()
            return typed_server_message(
                "MFA_SETUP_REQUIRED",
                MfaSetupRequired(challenge_token=token, expires_in_seconds=300),
                SuccessEnvelope[LoginResponse, ResponseMetadata],
                "auth_login",
                headers={"Cache-Control": "no-store"},
            )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return typed_server_message(
        "LOGIN_SUCCESS",
        Token(access_token=access_token, token_type="bearer"),
        SuccessEnvelope[LoginResponse, ResponseMetadata],
        "auth_login",
        headers={"Cache-Control": "no-store"},
    )
