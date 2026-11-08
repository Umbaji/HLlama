import base64
import binascii
import hashlib
import hmac
import os
import secrets
import struct
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from config import settings
from helpers.server_message import ServerMessageException
from models.admin_mfa import AdminMfaChallengeModel
from models.user import UserModel

CHALLENGE_TTL = timedelta(minutes=5)


def encryption_key() -> bytes:
    value = (
        settings.ADMIN_MFA_ENCRYPTION_KEY.get_secret_value()
        if settings.ADMIN_MFA_ENCRYPTION_KEY
        else ""
    )
    try:
        key = bytes.fromhex(value)
    except ValueError as exc:
        raise ServerMessageException("MFA_UNAVAILABLE", status=503) from exc
    if len(value) != 64 or len(key) != 32:
        raise ServerMessageException("MFA_UNAVAILABLE", status=503)
    return key


def create_totp_secret() -> str:
    return base64.b32encode(os.urandom(20)).decode("ascii").rstrip("=")


def encrypt_secret(secret: str, user_id: uuid.UUID) -> str:
    nonce = os.urandom(12)
    ciphertext = AESGCM(encryption_key()).encrypt(
        nonce, secret.encode("ascii"), user_id.bytes
    )
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt_secret(encrypted: str, user_id: uuid.UUID) -> str:
    try:
        raw = base64.urlsafe_b64decode(encrypted.encode("ascii"))
        secret = AESGCM(encryption_key()).decrypt(raw[:12], raw[12:], user_id.bytes)
        return secret.decode("ascii")
    except ServerMessageException:
        raise
    except Exception as exc:
        raise ServerMessageException("MFA_UNAVAILABLE", status=503) from exc


def matching_totp_counter(
    secret: str, code: str, now: datetime | None = None
) -> int | None:
    if len(code) != 6 or not code.isascii() or not code.isdigit():
        return None
    current = int((now or datetime.now(timezone.utc)).timestamp()) // 30
    try:
        key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    except (binascii.Error, ValueError) as exc:
        raise ServerMessageException("MFA_UNAVAILABLE", status=503) from exc
    matches = [
        current + offset
        for offset in (1, 0, -1)
        if hmac.compare_digest(_totp(key, current + offset), code)
    ]
    return matches[0] if matches else None


def is_valid_totp(secret: str, code: str, now: datetime | None = None) -> bool:
    return matching_totp_counter(secret, code, now) is not None


def _totp(key: bytes, counter: int) -> str:
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{binary % 1_000_000:06d}"


def create_challenge(
    db: Session,
    user_id: uuid.UUID,
    purpose: str,
    now: datetime | None = None,
) -> str:
    current = now or datetime.now(timezone.utc)
    db.execute(select(UserModel.id).where(UserModel.id == user_id).with_for_update()).scalar_one()
    expired = db.execute(
        select(AdminMfaChallengeModel.id)
        .where(AdminMfaChallengeModel.expires_at <= current)
        .order_by(AdminMfaChallengeModel.expires_at)
        .limit(500)
    ).scalars().all()
    if expired:
        db.execute(
            delete(AdminMfaChallengeModel).where(AdminMfaChallengeModel.id.in_(expired))
        )
    outstanding = db.execute(
        select(AdminMfaChallengeModel.id)
        .where(
            AdminMfaChallengeModel.user_id == user_id,
            AdminMfaChallengeModel.consumed_at.is_(None),
            AdminMfaChallengeModel.expires_at > current,
        )
        .order_by(AdminMfaChallengeModel.created_at.desc())
        .offset(4)
        .limit(500)
    ).scalars().all()
    if outstanding:
        db.execute(
            delete(AdminMfaChallengeModel).where(
                AdminMfaChallengeModel.id.in_(outstanding)
            )
        )
    token = secrets.token_urlsafe(32)
    db.add(
        AdminMfaChallengeModel(
            id=uuid.uuid4(),
            user_id=user_id,
            purpose=purpose,
            token_digest=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=current + CHALLENGE_TTL,
            created_at=current,
        )
    )
    return token


def get_challenge(
    db: Session,
    token: str,
    purpose: str,
    now: datetime | None = None,
) -> AdminMfaChallengeModel:
    digest = hashlib.sha256(token.encode()).hexdigest()
    current = now or datetime.now(timezone.utc)
    challenge = db.execute(
        select(AdminMfaChallengeModel)
        .where(
            AdminMfaChallengeModel.token_digest == digest,
            AdminMfaChallengeModel.purpose == purpose,
            AdminMfaChallengeModel.consumed_at.is_(None),
        )
        .with_for_update()
    ).scalar_one_or_none()
    if challenge is None:
        raise ServerMessageException("MFA_INVALID", status=401)
    if _as_utc(challenge.expires_at) <= current:
        raise ServerMessageException("MFA_CHALLENGE_EXPIRED", status=401)
    return challenge


def consume_challenge(challenge: AdminMfaChallengeModel, now: datetime | None = None) -> None:
    challenge.consumed_at = now or datetime.now(timezone.utc)


def recovery_codes() -> list[str]:
    return ["-".join(_chunks(base64.b32encode(os.urandom(16)).decode().rstrip("="))) for _ in range(10)]


def recovery_digest(code: str) -> str:
    normalized = code.replace("-", "").upper()
    return hashlib.sha256(normalized.encode("ascii")).hexdigest()


def otp_uri(secret: str, email: str) -> str:
    label = quote(f"HLlama:{email}", safe="")
    return (
        f"otpauth://totp/{label}?secret={secret}&issuer=HLlama"
        "&algorithm=SHA1&digits=6&period=30"
    )


def _chunks(value: str) -> list[str]:
    return [value[index : index + 5] for index in range(0, len(value), 5)]


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
