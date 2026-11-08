import uuid
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from helpers.anonymity import decrypt_number, mask_number
from models.activity_log import ActivityLogModel
from models.question import QuestionModel
from models.user import UserModel
from services.reminder_service import cancel_pending_reminders


def log_activity(db: Session, admin_id: uuid.UUID, action: str, target_type: str, target_id: str = None, details: str = None):
    log = ActivityLogModel(
        admin_id=admin_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=details,
    )
    db.add(log)
    db.commit()


def deactivate_user(db: Session, user_id: uuid.UUID, admin_id: uuid.UUID) -> UserModel | None:
    result = db.execute(select(UserModel).where(UserModel.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return None
    user.is_active = False
    db.commit()
    db.refresh(user)
    log_activity(db, admin_id, "DEACTIVATE_USER", "user", str(user_id))
    return user


def activate_user(db: Session, user_id: uuid.UUID, admin_id: uuid.UUID) -> UserModel | None:
    result = db.execute(select(UserModel).where(UserModel.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return None
    user.is_active = True
    db.commit()
    db.refresh(user)
    log_activity(db, admin_id, "ACTIVATE_USER", "user", str(user_id))
    return user


def soft_delete_user(db: Session, user_id: uuid.UUID, admin_id: uuid.UUID) -> UserModel | None:
    result = db.execute(select(UserModel).where(UserModel.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return None
    user.is_active = False
    user.deleted_at = datetime.now(timezone.utc)
    cancel_pending_reminders(db, user.pseudo_id, commit=False)
    db.commit()
    db.refresh(user)
    log_activity(db, admin_id, "DELETE_USER", "user", str(user_id))
    return user


def delete_question(db: Session, question_id: uuid.UUID, admin_id: uuid.UUID) -> bool:
    result = db.execute(select(QuestionModel).where(QuestionModel.id == question_id))
    question = result.scalar_one_or_none()
    if not question:
        return False
    db.delete(question)
    db.commit()
    log_activity(db, admin_id, "DELETE_QUESTION", "question", str(question_id))
    return True


def get_all_questions_paginated(db: Session, page: int = 1, limit: int = 20) -> dict:
    import math
    total = db.execute(select(func.count()).select_from(QuestionModel)).scalar()
    total_pages = math.ceil(total / limit) if total else 0
    offset = (page - 1) * limit

    results = db.execute(
        select(
            QuestionModel.id,
            QuestionModel.question,
            QuestionModel.response,
            QuestionModel.request_type,
            QuestionModel.created_at,
            UserModel.pseudo_id,
            UserModel.telnumber,
        )
        .join(UserModel, UserModel.id == QuestionModel.user_id)
        .order_by(QuestionModel.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()

    questions = [
        {
            "id": str(row.id),
            "question": row.question,
            "response": row.response,
            "request_type": row.request_type,
            "created_at": row.created_at.isoformat(),
            "user_pseudo_id": row.pseudo_id,
            "user_telnumber_masked": mask_number(decrypt_number(row.telnumber)),
        }
        for row in results
    ]

    return {
        "data": questions,
        "meta": {
            "current_page": page,
            "total_pages": total_pages,
            "total_count": total,
            "page_size": limit,
            "has_more": page < total_pages,
        },
    }


def get_activity_logs(db: Session, page: int = 1, limit: int = 20) -> dict:
    import math
    total = db.execute(select(func.count()).select_from(ActivityLogModel)).scalar()
    total_pages = math.ceil(total / limit) if total else 0
    offset = (page - 1) * limit

    results = db.execute(
        select(
            ActivityLogModel.id,
            ActivityLogModel.action,
            ActivityLogModel.target_type,
            ActivityLogModel.target_id,
            ActivityLogModel.details,
            ActivityLogModel.created_at,
            UserModel.fullname.label("admin_name"),
        )
        .outerjoin(UserModel, UserModel.id == ActivityLogModel.admin_id)
        .order_by(ActivityLogModel.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).all()

    logs = [
        {
            "id": str(row.id),
            "action": row.action,
            "target_type": row.target_type,
            "target_id": row.target_id,
            "details": row.details,
            "created_at": row.created_at.isoformat(),
            "admin_name": row.admin_name,
        }
        for row in results
    ]

    return {
        "data": logs,
        "meta": {
            "current_page": page,
            "total_pages": total_pages,
            "total_count": total,
            "page_size": limit,
            "has_more": page < total_pages,
        },
    }


def promote_to_admin(db: Session, user_id: uuid.UUID, admin_id: uuid.UUID) -> UserModel | None:
    result = db.execute(select(UserModel).where(UserModel.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return None
    user.is_admin = True
    db.commit()
    db.refresh(user)
    log_activity(db, admin_id, "PROMOTE_TO_ADMIN", "user", str(user_id))
    return user


def demote_from_admin(db: Session, user_id: uuid.UUID, admin_id: uuid.UUID) -> UserModel | None:
    result = db.execute(select(UserModel).where(UserModel.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return None
    user.is_admin = False
    db.commit()
    db.refresh(user)
    log_activity(db, admin_id, "DEMOTE_FROM_ADMIN", "user", str(user_id))
    return user
