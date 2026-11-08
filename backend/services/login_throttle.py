import hashlib
import hmac
import ipaddress
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Request
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from config import settings
from helpers.email import normalize_email
from helpers.server_message import ServerMessageException
from models.login_attempt import LoginAttemptBucketModel

WINDOW = timedelta(minutes=15)
RETENTION = timedelta(hours=24)
COOLDOWNS = (15, 30, 60, 120)


@dataclass(frozen=True, slots=True)
class LoginReservation:
    identity_key: str
    identity_blocked_until: datetime | None


def source_ip(request: Request) -> str:
    peer = request.client.host if request.client else None
    if not peer:
        raise ValueError("missing peer")
    if settings.LOGIN_TRUSTED_PROXY_HOPS == 0:
        return str(ipaddress.ip_address(peer))
    forwarded = request.headers.get("x-forwarded-for", "")
    chain = [item.strip() for item in forwarded.split(",") if item.strip()]
    if len(chain) < settings.LOGIN_TRUSTED_PROXY_HOPS:
        raise ValueError("invalid proxy chain")
    # Azure Container Apps appends its ingress address; only its rightmost
    # forwarded hop is trusted, never a caller-supplied left-side address.
    return str(ipaddress.ip_address(chain[-1]))


def _bucket_key(kind: str, value: str, secret: bytes) -> str:
    return hmac.new(secret, f"{kind}:{value}".encode(), hashlib.sha256).hexdigest()


def _secret_bytes() -> bytes:
    configured = (
        settings.ADMIN_LOGIN_BUCKET_KEY.get_secret_value()
        if settings.ADMIN_LOGIN_BUCKET_KEY
        else None
    )
    if configured is None or len(configured) != 64:
        raise ValueError("invalid throttle key")
    try:
        secret = bytes.fromhex(configured)
    except ValueError as exc:
        raise ValueError("invalid throttle key") from exc
    if len(secret) != 32:
        raise ValueError("invalid throttle key")
    return secret


def reserve_login_attempt(
    db: Session,
    request: Request,
    username: str,
    now: datetime | None = None,
) -> LoginReservation:
    try:
        secret = _secret_bytes()
        ip = source_ip(request)
        current = now or datetime.now(timezone.utc)
        keys = {
            "identity": _bucket_key("identity", normalize_email(username), secret),
            "ip": _bucket_key("ip", ip, secret),
        }
        _remove_expired(db, current)
        _ensure_rows(db, keys, current)
        return _reserve_rows(db, keys, current)
    except ServerMessageException:
        raise
    except Exception as exc:
        db.rollback()
        raise ServerMessageException("LOGIN_THROTTLE_UNAVAILABLE") from exc


def _reserve_rows(
    db: Session,
    keys: dict[str, str],
    now: datetime,
) -> LoginReservation:
    rows = db.execute(
        select(LoginAttemptBucketModel)
        .where(LoginAttemptBucketModel.bucket_key.in_(keys.values()))
        .order_by(LoginAttemptBucketModel.bucket_key)
        .with_for_update()
    ).scalars().all()
    identity_blocked_until = _check_bucket_limits(db, rows, now)
    for row in rows:
        if row.bucket_kind == "identity" and identity_blocked_until:
            continue
        row.attempt_count += 1
        row.expires_at = now + RETENTION
    db.commit()
    return LoginReservation(keys["identity"], identity_blocked_until)


def _check_bucket_limits(
    db: Session,
    rows: list[LoginAttemptBucketModel],
    now: datetime,
) -> datetime | None:
    by_kind = {row.bucket_kind: row for row in rows}
    identity_blocked_until: datetime | None = None
    for kind, limit in (("identity", 5), ("ip", 30)):
        row = by_kind[kind]
        blocked_until = _as_utc(row.blocked_until) if row.blocked_until else None
        if blocked_until and blocked_until > now:
            if kind == "identity":
                identity_blocked_until = blocked_until
                continue
            db.rollback()
            raise_login_limited(blocked_until, now)
        if now - _as_utc(row.window_started_at) >= WINDOW:
            row.window_started_at = now
            row.attempt_count = 0
            row.blocked_until = None
        if row.attempt_count >= limit:
            blocked_until = _block_bucket(row, now)
            if kind == "identity":
                identity_blocked_until = blocked_until
                continue
            db.commit()
            raise_login_limited(blocked_until, now)
    return identity_blocked_until


def _block_bucket(
    row: LoginAttemptBucketModel,
    now: datetime,
) -> datetime:
    cooldown = COOLDOWNS[min(row.cooldown_level, len(COOLDOWNS) - 1)]
    row.cooldown_level = min(row.cooldown_level + 1, len(COOLDOWNS))
    blocked_until = now + timedelta(minutes=cooldown)
    row.blocked_until = blocked_until
    row.expires_at = now + RETENTION
    return blocked_until


def clear_identity_bucket(db: Session, key: str) -> None:
    try:
        db.execute(
            delete(LoginAttemptBucketModel).where(
                LoginAttemptBucketModel.bucket_key == key
            )
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        raise ServerMessageException("LOGIN_THROTTLE_UNAVAILABLE") from exc


def _ensure_rows(db: Session, keys: dict[str, str], now: datetime) -> None:
    dialect = db.get_bind().dialect.name
    insert = pg_insert if dialect == "postgresql" else sqlite_insert
    for kind, key in sorted(keys.items(), key=lambda item: item[1]):
        statement = insert(LoginAttemptBucketModel).values(
            bucket_key=key,
            bucket_kind=kind,
            window_started_at=now,
            attempt_count=0,
            cooldown_level=0,
            expires_at=now + RETENTION,
        )
        db.execute(statement.on_conflict_do_nothing(index_elements=["bucket_key"]))
    db.flush()


def _remove_expired(db: Session, now: datetime) -> None:
    expired = db.execute(
        select(LoginAttemptBucketModel.bucket_key)
        .where(LoginAttemptBucketModel.expires_at <= now)
        .order_by(LoginAttemptBucketModel.expires_at)
        .limit(500)
    ).scalars().all()
    if expired:
        db.execute(
            delete(LoginAttemptBucketModel).where(
                LoginAttemptBucketModel.bucket_key.in_(expired)
            )
        )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def raise_login_limited(blocked_until: datetime, now: datetime) -> None:
    seconds = max(1, math.ceil((blocked_until - now).total_seconds()))
    retry_after = min(seconds, 7200)
    raise ServerMessageException(
        "LOGIN_RATE_LIMITED",
        meta={"retry_after_ms": retry_after * 1000},
        headers={"Retry-After": str(retry_after)},
    )
