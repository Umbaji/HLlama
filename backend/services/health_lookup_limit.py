import hashlib
import hmac
import math
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from models.health_lookup_bucket import HealthLookupBucketModel

WINDOW = timedelta(minutes=1)
TTL = timedelta(minutes=2)


def reserve_health_lookup(
    db: Session,
    credential: str,
    operation: str,
    limit: int,
    now: datetime | None = None,
) -> int:
    current = now or datetime.now(timezone.utc)
    key = hmac.new(
        credential.encode("utf-8"),
        f"health-lookup:{operation}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    _remove_expired(db, current)
    table = HealthLookupBucketModel
    insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    statement = insert(table).values(
        bucket_key=key,
        operation=operation,
        window_started_at=current,
        request_count=1,
        expires_at=current + TTL,
    )
    expired_window = table.window_started_at <= current - WINDOW
    next_count = case(
        (table.request_count < limit + 1, table.request_count + 1),
        else_=limit + 1,
    )
    statement = statement.on_conflict_do_update(
        index_elements=[table.bucket_key],
        set_={
            "operation": operation,
            "window_started_at": case(
                (expired_window, current), else_=table.window_started_at
            ),
            "request_count": case((expired_window, 1), else_=next_count),
            "expires_at": current + TTL,
        },
    ).returning(table.request_count, table.window_started_at)
    count, window_started_at = db.execute(statement).one()
    db.commit()
    start = window_started_at
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    retry_ms = max(1, math.ceil((start + WINDOW - current).total_seconds() * 1000))
    return retry_ms if count > limit else 0


def _remove_expired(db: Session, now: datetime) -> None:
    expired = db.execute(
        select(HealthLookupBucketModel.bucket_key)
        .where(HealthLookupBucketModel.expires_at <= now)
        .order_by(HealthLookupBucketModel.expires_at)
        .limit(100)
    ).scalars().all()
    if expired:
        db.execute(
            delete(HealthLookupBucketModel).where(
                HealthLookupBucketModel.bucket_key.in_(expired)
            )
        )
