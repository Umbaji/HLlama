from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.question import QuestionModel
from models.user import UserModel


def get_overview_stats(db: Session) -> dict:
    total_users = db.execute(
        select(func.count()).select_from(UserModel).where(UserModel.is_admin == False)
    ).scalar()

    active_users = db.execute(
        select(func.count()).select_from(UserModel).where(
            UserModel.is_admin == False, UserModel.is_active == True
        )
    ).scalar()

    inactive_users = db.execute(
        select(func.count()).select_from(UserModel).where(
            UserModel.is_admin == False, UserModel.is_active == False
        )
    ).scalar()

    total_admins = db.execute(
        select(func.count()).select_from(UserModel).where(UserModel.is_admin == True)
    ).scalar()

    total_questions = db.execute(
        select(func.count()).select_from(QuestionModel)
    ).scalar()

    now = datetime.now(timezone.utc)
    last_7_days = now - timedelta(days=7)
    last_30_days = now - timedelta(days=30)

    new_users_7d = db.execute(
        select(func.count()).select_from(UserModel).where(
            UserModel.is_admin == False, UserModel.created_at >= last_7_days
        )
    ).scalar()

    new_users_30d = db.execute(
        select(func.count()).select_from(UserModel).where(
            UserModel.is_admin == False, UserModel.created_at >= last_30_days
        )
    ).scalar()

    questions_7d = db.execute(
        select(func.count()).select_from(QuestionModel).where(
            QuestionModel.created_at >= last_7_days
        )
    ).scalar()

    questions_30d = db.execute(
        select(func.count()).select_from(QuestionModel).where(
            QuestionModel.created_at >= last_30_days
        )
    ).scalar()

    return {
        "total_users": total_users,
        "active_users": active_users,
        "inactive_users": inactive_users,
        "total_admins": total_admins,
        "total_questions": total_questions,
        "new_users_7d": new_users_7d,
        "new_users_30d": new_users_30d,
        "questions_7d": questions_7d,
        "questions_30d": questions_30d,
    }
