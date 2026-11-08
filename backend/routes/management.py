import csv
import io
import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from helpers.anonymity import decrypt_number, mask_number
from helpers.server_message import ServerMessageException, server_message
from models.question import QuestionModel
from models.user import UserModel
from schemas.feedback import FeedbackResponse
from services.auth_service import require_admin
from services.feedback_service import list_feedback
from services.admin_service import (
    activate_user,
    deactivate_user,
    delete_question,
    demote_from_admin,
    get_activity_logs,
    get_all_questions_paginated,
    promote_to_admin,
    soft_delete_user,
)

router = APIRouter(prefix="/api/manage", tags=["management"])


# Contrôle partagé avec les routes utilisateurs et admins.
_require_admin = require_admin


@router.post("/users/{user_id}/deactivate")
def deactivate(user_id: uuid.UUID, db: Session = Depends(get_db), admin=Depends(_require_admin)):
    user = deactivate_user(db, user_id, admin.id)
    if not user:
        raise ServerMessageException("USER_NOT_FOUND")
    return server_message("SUCCESS", data={"id": str(user.id), "is_active": user.is_active})


@router.post("/users/{user_id}/activate")
def activate(user_id: uuid.UUID, db: Session = Depends(get_db), admin=Depends(_require_admin)):
    user = activate_user(db, user_id, admin.id)
    if not user:
        raise ServerMessageException("USER_NOT_FOUND")
    return server_message("SUCCESS", data={"id": str(user.id), "is_active": user.is_active})


@router.delete("/users/{user_id}")
def delete_user_route(user_id: uuid.UUID, db: Session = Depends(get_db), admin=Depends(_require_admin)):
    user = soft_delete_user(db, user_id, admin.id)
    if not user:
        raise ServerMessageException("USER_NOT_FOUND")
    return server_message("SUCCESS", data={"id": str(user.id), "deleted_at": user.deleted_at.isoformat()})


@router.post("/users/{user_id}/promote")
def promote(user_id: uuid.UUID, db: Session = Depends(get_db), admin=Depends(_require_admin)):
    user = promote_to_admin(db, user_id, admin.id)
    if not user:
        raise ServerMessageException("USER_NOT_FOUND")
    return server_message("SUCCESS", data={"id": str(user.id), "is_admin": user.is_admin})


@router.post("/users/{user_id}/demote")
def demote(user_id: uuid.UUID, db: Session = Depends(get_db), admin=Depends(_require_admin)):
    user = demote_from_admin(db, user_id, admin.id)
    if not user:
        raise ServerMessageException("USER_NOT_FOUND")
    return server_message("SUCCESS", data={"id": str(user.id), "is_admin": user.is_admin})


@router.get("/questions")
def list_all_questions(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin=Depends(_require_admin),
):
    result = get_all_questions_paginated(db, page=page, limit=limit)
    return server_message("SUCCESS", data=result["data"], meta=result["meta"])


@router.delete("/questions/{question_id}")
def delete_question_route(question_id: uuid.UUID, db: Session = Depends(get_db), admin=Depends(_require_admin)):
    deleted = delete_question(db, question_id, admin.id)
    if not deleted:
        raise ServerMessageException("RESOURCE_NOT_FOUND")
    return server_message("SUCCESS", data={"deleted": str(question_id)})


@router.get("/logs")
def list_logs(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin=Depends(_require_admin),
):
    result = get_activity_logs(db, page=page, limit=limit)
    return server_message("SUCCESS", data=result["data"], meta=result["meta"])


@router.get("/feedback")
def list_feedback_responses(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    question_key: str | None = Query(None, max_length=50),
    db: Session = Depends(get_db),
    _admin=Depends(_require_admin),
):
    """Feedback answers (pseudonymous, no phone numbers) and per-question aggregates."""
    result = list_feedback(db, page=page, limit=limit, question_key=question_key)
    return server_message(
        "FEEDBACK_FETCHED",
        data={
            "items": [FeedbackResponse.model_validate(r).model_dump() for r in result["items"]],
            "aggregates": result["aggregates"],
        },
        meta=result["meta"],
    )


@router.get("/export/users")
def export_users_csv(db: Session = Depends(get_db), _admin=Depends(_require_admin)):
    users = db.execute(
        select(UserModel).where(UserModel.deleted_at.is_(None)).order_by(UserModel.created_at.desc())
    ).scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["pseudo_id", "telnumber_masked", "location", "age", "is_admin", "is_active", "created_at"])
    for u in users:
        writer.writerow([
            u.pseudo_id,
            mask_number(decrypt_number(u.telnumber)),
            u.location,
            u.age,
            u.is_admin,
            u.is_active,
            u.created_at.isoformat(),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=users_export.csv"},
    )


@router.get("/export/questions")
def export_questions_csv(db: Session = Depends(get_db), _admin=Depends(_require_admin)):
    stmt = (
        select(QuestionModel, UserModel.pseudo_id, UserModel.telnumber)
        .join(UserModel, QuestionModel.user_id == UserModel.id)
        .order_by(QuestionModel.created_at.desc())
    )
    rows = db.execute(stmt).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "question", "response", "request_type", "user_pseudo_id", "user_telnumber_masked", "created_at"])
    for q, pseudo_id, telnumber in rows:
        writer.writerow([
            str(q.id),
            q.question,
            q.response,
            q.request_type,
            pseudo_id,
            mask_number(decrypt_number(telnumber)),
            q.created_at.isoformat(),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=questions_export.csv"},
    )
