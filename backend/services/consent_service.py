import time
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config import settings
from models.consent import ConsentRecordModel

ALGORITHM = "HS256"
DEFAULT_TTL_SECONDS = 24 * 60 * 60  # 24h, coherent avec la fenetre de conversation WhatsApp

VALID_DECISIONS = ("accepted", "refused")

# Version of the policy text the consent page shows. Stored with every decision:
# a decision only proves consent to the text that was on screen. Must match the
# "policy_version" label of content/consent/ui.*.json (a test binds them).
CURRENT_POLICY_VERSION = "1.0"


class ConsentTokenError(Exception):
    """Token de consentement absent, invalide ou expire."""


class ConsentTokenUsedError(Exception):
    """Le lien a deja enregistre une decision : il ne sert qu'une fois."""


# What a link can be when the page is opened. The page renders a different
# state for each, so a woman learns her link is spent before she taps a button.
TOKEN_MISSING = "missing"
TOKEN_INVALID = "invalid"
TOKEN_EXPIRED = "expired"
TOKEN_USED = "used"
TOKEN_VALID = "valid"


def generate_consent_token(pseudo_id: str, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> str:
    """Le token porte le pseudo_id (jamais le numero en clair) + une expiration courte."""
    payload = {
        "pseudo_id": pseudo_id,
        "purpose": "consent",
        # Identifies this link. Recorded with the decision, so the same link
        # cannot record a second one.
        "jti": uuid.uuid4().hex,
        "iat": int(time.time()),
        "exp": int(time.time()) + ttl_seconds,
    }
    return jwt.encode(payload, settings.CONSENT_TOKEN_SECRET, algorithm=ALGORITHM)


def verify_consent_token(token: str) -> str:
    """Retourne le pseudo_id si le token est valide, leve ConsentTokenError sinon."""
    return read_consent_token(token)[0]


def read_consent_token(token: str) -> tuple[str, str | None]:
    """Le pseudo_id et le jti du lien. Le jti manque sur les liens emis avant
    que les liens ne deviennent a usage unique."""
    try:
        payload = jwt.decode(token, settings.CONSENT_TOKEN_SECRET, algorithms=[ALGORITHM])
    except ExpiredSignatureError as exc:
        raise ConsentTokenError("Token expired") from exc
    except InvalidTokenError as exc:
        raise ConsentTokenError("Invalid token") from exc

    if payload.get("purpose") != "consent":
        raise ConsentTokenError("Wrong token purpose")

    pseudo_id = payload.get("pseudo_id")
    if not isinstance(pseudo_id, str) or not pseudo_id:
        raise ConsentTokenError("Missing pseudo_id in token")

    jti = payload.get("jti")
    return pseudo_id, jti if isinstance(jti, str) and jti else None


def token_state(db: Session, token: str | None) -> str:
    """What the page should show for this link, without recording anything."""
    if not token:
        return TOKEN_MISSING
    try:
        _, jti = read_consent_token(token)
    except ConsentTokenError as exc:
        return TOKEN_EXPIRED if str(exc) == "Token expired" else TOKEN_INVALID

    if jti and _jti_used(db, jti):
        return TOKEN_USED
    return TOKEN_VALID


def _jti_used(db: Session, jti: str) -> bool:
    stmt = select(ConsentRecordModel.id).where(ConsentRecordModel.token_jti == jti).limit(1)
    return db.execute(stmt).first() is not None


def record_consent(
    db: Session, pseudo_id: str, decision: str, token_jti: str | None = None
) -> ConsentRecordModel:
    """Records one decision. Raises ConsentTokenUsedError when the link already
    recorded one: the unique index decides, so two simultaneous taps cannot both
    get through."""
    record = ConsentRecordModel(
        id=uuid.uuid4(),
        pseudo_id=pseudo_id,
        decision=decision,
        token_jti=token_jti,
        policy_version=CURRENT_POLICY_VERSION,
        recorded_at=_next_recorded_at(db, pseudo_id),
    )
    db.add(record)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ConsentTokenUsedError(str(exc)) from exc
    db.refresh(record)
    return record


def _next_recorded_at(db: Session, pseudo_id: str) -> datetime:
    """Strictly increasing timestamp for this pseudo_id.

    Two jobs can land on the same clock tick. When they do, the "latest"
    decision is undefined and the fail-closed tie-break below would hand the
    gate back to a previous "refused" even when the newest record says
    "accepted". Recording each next answer one microsecond above the last one
    for the same pseudo_id keeps "latest" meaningful without sleeps or locks."""
    previous = db.execute(
        select(ConsentRecordModel.recorded_at)
        .where(ConsentRecordModel.pseudo_id == pseudo_id)
        .order_by(ConsentRecordModel.recorded_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if previous is None:
        return now
    if previous.tzinfo is None:
        previous = previous.replace(tzinfo=timezone.utc)
    one_after_previous = previous + timedelta(microseconds=1)
    return one_after_previous if now <= one_after_previous else now


# Two records can share a timestamp: the system clock is not always finer than
# the gap between two writes. Ordering by the timestamp alone then leaves the
# "latest" decision undefined, and that decision is what opens or closes the
# assistant. On a tie the most restrictive decision wins, which keeps the gate
# fail-closed like the rest of the consent path ("refused" sorts after
# "accepted", so DESC puts it first).
_LATEST_ORDER = (ConsentRecordModel.recorded_at.desc(), ConsentRecordModel.decision.desc())


def get_latest_consent(db: Session, pseudo_id: str) -> ConsentRecordModel | None:
    stmt = (
        select(ConsentRecordModel)
        .where(ConsentRecordModel.pseudo_id == pseudo_id)
        .order_by(*_LATEST_ORDER)
        .limit(1)
    )
    return db.execute(stmt).scalar_one_or_none()


def build_consent_url(token: str) -> str:
    base = settings.CONSENT_PAGE_BASE_URL.rstrip("/")
    return f"{base}/consent?t={token}"


def issue_consent_link(pseudo_id: str) -> str:
    return build_consent_url(generate_consent_token(pseudo_id))


def latest_decision_subquery(pseudo_id_column):
    """Correlated scalar subquery: latest consent decision for a pseudo_id column."""
    return (
        select(ConsentRecordModel.decision)
        .where(ConsentRecordModel.pseudo_id == pseudo_id_column)
        .order_by(*_LATEST_ORDER)
        .limit(1)
        .scalar_subquery()
    )


def get_consent_status(db: Session, pseudo_id: str) -> str:
    """'accepted' | 'refused' | 'pending' (never answered)."""
    record = get_latest_consent(db, pseudo_id)
    return record.decision if record else "pending"
