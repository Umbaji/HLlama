import math
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from config import settings
from models.feedback import FeedbackResponseModel
from models.reminder import ReminderModel
from schemas.feedback import FeedbackCreate
from services.consent_service import has_accepted_consent

# Shown on the lock screen, so it stays neutral; the bot renders the rating buttons.
FEEDBACK_MESSAGE = "HLlama aimerait avoir votre avis. Répondez à ce message pour le voir."


def schedule_feedback(db: Session, pseudo_id: str, now: datetime | None = None) -> bool:
    """Queues one feedback question after a conversation, at most once per cooldown."""
    now = now or datetime.now(timezone.utc)
    if not has_accepted_consent(db, pseudo_id):
        return False
    feedback = select(ReminderModel.id).where(
        ReminderModel.pseudo_id == pseudo_id, ReminderModel.kind == "feedback"
    )
    already_open = db.execute(
        feedback.where(ReminderModel.status.in_(("pending", "sending"))).limit(1)
    ).first()
    if already_open:
        return False
    cooldown_start = now - timedelta(days=settings.FEEDBACK_COOLDOWN_DAYS)
    recently_sent = db.execute(
        feedback.where(ReminderModel.sent_at >= cooldown_start).limit(1)
    ).first()
    if recently_sent:
        return False
    db.add(
        ReminderModel(
            pseudo_id=pseudo_id,
            kind="feedback",
            message=FEEDBACK_MESSAGE,
            scheduled_at=now + timedelta(minutes=settings.FEEDBACK_DELAY_MINUTES),
        )
    )
    db.commit()
    return True


def record_feedback(db: Session, data: FeedbackCreate) -> FeedbackResponseModel:
    response = FeedbackResponseModel(
        pseudo_id=data.pseudo_id,
        question_key=data.question_key,
        rating=data.rating,
        answer=data.answer,
    )
    db.add(response)
    db.commit()
    db.refresh(response)
    return response


def list_feedback(
    db: Session,
    page: int = 1,
    limit: int = 20,
    question_key: str | None = None,
) -> dict:
    base = select(FeedbackResponseModel)
    if question_key:
        base = base.where(FeedbackResponseModel.question_key == question_key)
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar() or 0
    total_pages = math.ceil(total / limit) if total else 0
    items = db.execute(
        base.order_by(FeedbackResponseModel.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    ).scalars().all()
    return {
        "items": items,
        "aggregates": _aggregates(db, question_key),
        "meta": {
            "current_page": page,
            "total_pages": total_pages,
            "total_count": total,
            "page_size": limit,
            "has_more": page < total_pages,
        },
    }


def _aggregates(db: Session, question_key: str | None) -> list[dict]:
    query = select(
        FeedbackResponseModel.question_key,
        FeedbackResponseModel.rating,
        func.count(),
    ).group_by(FeedbackResponseModel.question_key, FeedbackResponseModel.rating)
    if question_key:
        query = query.where(FeedbackResponseModel.question_key == question_key)
    per_key: dict[str, dict] = {}
    for key, rating, count in db.execute(query).all():
        entry = per_key.setdefault(key, {"question_key": key, "count": 0, "ratings": {}})
        entry["count"] += count
        if rating is not None:
            entry["ratings"][str(rating)] = count
    for entry in per_key.values():
        rated = sum(entry["ratings"].values())
        total = sum(int(r) * c for r, c in entry["ratings"].items())
        entry["rated_count"] = rated
        entry["average_rating"] = round(total / rated, 2) if rated else None
    return sorted(per_key.values(), key=lambda e: e["question_key"])
