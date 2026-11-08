import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from helpers.anonymity import pseudo_id_for
from helpers.server_message import ServerMessageException, typed_server_message
from schemas.common import ResponseMetadata, SuccessEnvelope
from schemas.reminder import ReminderCreate, ReminderResponse
from services.auth_service import get_current_active_user
from services.reminder_service import (
    ReminderInPastError,
    cancel_reminder,
    create_reminder,
    get_reminder,
    list_reminders,
)
from services.user_service import UserDeletedError

router = APIRouter(prefix="/api/reminders", tags=["reminders"])


def _serialize(reminder) -> ReminderResponse:
    return ReminderResponse.model_validate(reminder)


def _require_admin(current_user) -> None:
    if not current_user.is_admin:
        raise ServerMessageException("UNAUTHORIZED_ACCESS", status=403)


@router.get(
    "", response_model=SuccessEnvelope[list[ReminderResponse], ResponseMetadata]
)
def list_all_reminders(
    status: str | None = Query(
        None, description="Filter by status (pending/sending/sent/undelivered/failed/cancelled)"
    ),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    _require_admin(current_user)
    reminders = list_reminders(db, status_filter=status, limit=limit)
    return typed_server_message(
        "REMINDERS_FETCHED",
        [_serialize(reminder) for reminder in reminders],
        SuccessEnvelope[list[ReminderResponse], ResponseMetadata],
        "reminders_admin_list",
    )


@router.post(
    "", response_model=SuccessEnvelope[ReminderResponse, ResponseMetadata], status_code=201
)
def create_new_reminder(
    data: ReminderCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Any kind, for an existing user identified by pseudo_id."""
    _require_admin(current_user)
    if data.telnumber and pseudo_id_for(data.telnumber) != data.pseudo_id:
        raise ServerMessageException("PSEUDO_ID_MISMATCH", status=400)
    try:
        reminder = create_reminder(db, data, create_user=False)
    except ReminderInPastError:
        raise ServerMessageException("REMINDER_IN_PAST")
    except UserDeletedError:
        raise ServerMessageException("USER_DELETED")
    except ValueError:
        raise ServerMessageException("USER_NOT_FOUND")
    return typed_server_message(
        "REMINDER_CREATED",
        _serialize(reminder),
        SuccessEnvelope[ReminderResponse, ResponseMetadata],
        "reminders_admin_create",
        status=201,
    )


@router.get(
    "/{reminder_id}",
    response_model=SuccessEnvelope[ReminderResponse, ResponseMetadata],
)
def get_one_reminder(
    reminder_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    _require_admin(current_user)
    reminder = get_reminder(db, reminder_id)
    if not reminder:
        raise ServerMessageException("REMINDER_NOT_FOUND")
    return typed_server_message(
        "REMINDERS_FETCHED",
        _serialize(reminder),
        SuccessEnvelope[ReminderResponse, ResponseMetadata],
        "reminders_admin_get",
    )


@router.post(
    "/{reminder_id}/cancel",
    response_model=SuccessEnvelope[ReminderResponse, ResponseMetadata],
)
def cancel_existing_reminder(
    reminder_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    _require_admin(current_user)
    try:
        reminder = cancel_reminder(db, reminder_id)
    except ValueError:
        raise ServerMessageException("REMINDER_NOT_FOUND")
    return typed_server_message(
        "REMINDER_CANCELLED",
        _serialize(reminder),
        SuccessEnvelope[ReminderResponse, ResponseMetadata],
        "reminders_admin_cancel",
    )
