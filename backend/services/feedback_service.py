import math

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.feedback import FeedbackResponseModel
from schemas.feedback import FeedbackCreate


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
