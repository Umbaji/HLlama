"""What she declared about her health, kept only with her agreement.

The assistant asks the same questions again and again when it holds nothing:
allergies, what she takes, how many times she has given birth. A fact she
declared once, with her agreement, is worth keeping - and a fact she got wrong
is worth removing.

The fact is stored as she said it. The application does not parse it, does not
interpret it and does not turn it into a number: that is the model's work, and
the model reads it as data.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.health_fact import HealthFactModel

FACT_MAX_CHARS = 300


class FactNotFound(ValueError):
    """No fact of hers carries that id."""


def record_fact(db: Session, pseudo_id: str, user_id: uuid.UUID, fact: str) -> HealthFactModel:
    """Keeps a fact, with the moment she agreed to it."""
    text = (fact or "").strip()
    if not text:
        raise ValueError("FACT_REQUIRED")
    row = HealthFactModel(
        user_id=user_id,
        pseudo_id=pseudo_id,
        fact=text[:FACT_MAX_CHARS],
        consented_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_facts(db: Session, pseudo_id: str) -> list[HealthFactModel]:
    """The facts she declared, the most recent first."""
    result = db.execute(
        select(HealthFactModel)
        .where(
            HealthFactModel.pseudo_id == pseudo_id,
            HealthFactModel.active.is_(True),
        )
        .order_by(HealthFactModel.created_at.desc())
    )
    return list(result.scalars().all())


def remove_fact(db: Session, fact_id: uuid.UUID, pseudo_id: str) -> HealthFactModel:
    """Removes one of her facts. The row stays, marked as removed."""
    row = db.execute(
        select(HealthFactModel).where(
            HealthFactModel.id == fact_id,
            HealthFactModel.pseudo_id == pseudo_id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise FactNotFound("HEALTH_FACT_NOT_FOUND")
    row.active = False
    row.removed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


def serialize(row: HealthFactModel) -> dict:
    return {
        "id": str(row.id),
        "fact": row.fact,
        "consented_at": row.consented_at,
        "created_at": row.created_at,
    }
