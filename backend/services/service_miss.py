"""The wordings that named a service and were not understood.

The bot knows the services it has; it does not know all the words she uses for
them. Every time a message is refused and looks like a service request, the
scrubbed wording is recorded here, so the services can grow from what she
really says.

Two rules, both absolute:

- **No content.** The wording arrives scrubbed: no digits, no names, no links.
  What is kept is the shape of the sentence.
- **No health.** Only the wordings that name a service are recorded. A health
  question that was refused is counted, never written down.
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.service_miss import ServiceMissModel

WORDING_MAX_CHARS = 200


def record_miss(db: Session, service: str | None, wording: str) -> ServiceMissModel:
    """Records a wording, counting the ones that were already seen."""
    text = (wording or "").strip()[:WORDING_MAX_CHARS]
    if not text:
        raise ValueError("WORDING_REQUIRED")
    existing = db.execute(
        select(ServiceMissModel).where(
            ServiceMissModel.wording == text,
            ServiceMissModel.service == service,
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.hits += 1
        existing.last_seen_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing)
        return existing
    miss = ServiceMissModel(service=service, wording=text)
    db.add(miss)
    db.commit()
    db.refresh(miss)
    return miss


def list_misses(db: Session, limit: int = 50) -> list[tuple[ServiceMissModel, int]]:
    """The wordings, the ones that come back most often first."""
    rows = db.execute(
        select(ServiceMissModel)
        .order_by(ServiceMissModel.hits.desc(), ServiceMissModel.last_seen_at.desc())
        .limit(limit)
    ).scalars().all()
    return [(miss, miss.hits) for miss in rows]
