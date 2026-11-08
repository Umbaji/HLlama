import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from helpers.anonymity import pseudo_id_for
from helpers.server_message import (
    ServerMessageException,
    server_message,
    typed_server_message,
)
from helpers.timezones import iana_zone_for_telnumber
from schemas.bot_profile import BotProfileResponse, BotProfileUpdate
from schemas.common import ResponseMetadata, SuccessEnvelope
from schemas.feedback import (
    FeedbackCreate,
    FeedbackResponse,
    FeedbackScheduleRequest,
    FeedbackScheduleResponse,
)
from schemas.knowledge import KnowledgeSearchResult
from schemas.question import BotExchangeCreate, QuestionResponse
from schemas.reminder import (
    BotClaimedReminderResponse,
    ReminderCreate,
    ReminderDeliveryFailureResponse,
    ReminderDeliveryFailed,
    ReminderFailedReport,
    ReminderResponse,
    ReminderSentReport,
)
from services.bot_auth import verify_bot_api_key
from services.feedback_service import record_feedback, schedule_feedback
from services.knowledge import search_chunks
from services.question_service import (
    create_bot_exchange,
    get_recent_exchanges,
    search_exchanges,
)
from services.reminder_service import (
    ReminderInPastError,
    cancel_pending_reminders,
    cancel_user_reminder,
    claim_due_reminders,
    create_reminder,
    delivery_context,
    list_user_reminders,
    mark_reminder_failed,
    mark_reminder_sent,
    mark_reminder_undelivered,
)
from services.user_service import (
    UserDeletedError,
    find_user_by_pseudo_id,
    get_bot_profile,
    get_or_create_bot_user,
    update_bot_preferred_name,
)

router = APIRouter(prefix="/api/bot", tags=["bot"])


def _serialize(question) -> QuestionResponse:
    return QuestionResponse.model_validate(question)


def _serialize_reminder(reminder) -> ReminderResponse:
    return ReminderResponse.model_validate(reminder)


def _check_pseudo_id(pseudo_id: str, telnumber: str | None) -> None:
    if telnumber and pseudo_id_for(telnumber) != pseudo_id:
        raise ServerMessageException("PSEUDO_ID_MISMATCH", status=400)


def _bot_user(db: Session, pseudo_id: str, telnumber: str | None):
    _check_pseudo_id(pseudo_id, telnumber)
    try:
        return get_or_create_bot_user(db, pseudo_id, telnumber)
    except UserDeletedError:
        raise ServerMessageException("USER_DELETED")


@router.post(
    "/exchanges",
    response_model=SuccessEnvelope[QuestionResponse, ResponseMetadata],
    status_code=201,
)
def add_bot_exchange(
    data: BotExchangeCreate,
    db: Session = Depends(get_db),
    _bot: bool = Depends(verify_bot_api_key),
):
    user = _bot_user(db, data.pseudo_id, data.telnumber)
    question = create_bot_exchange(
        db,
        user.id,
        data.question,
        response=data.response,
        request_type=data.request_type,
    )
    return typed_server_message(
        "EXCHANGE_CREATED",
        _serialize(question),
        SuccessEnvelope[QuestionResponse, ResponseMetadata],
        "bot_exchange_create",
        status=201,
        headers={"Cache-Control": "no-store"},
    )


@router.get(
    "/users/{pseudo_id}/history",
    response_model=SuccessEnvelope[list[QuestionResponse], ResponseMetadata],
)
def list_history(
    pseudo_id: str,
    limit: int = Query(8, ge=1, le=20),
    db: Session = Depends(get_db),
    _bot: bool = Depends(verify_bot_api_key),
):
    user = find_user_by_pseudo_id(db, pseudo_id)
    if not user:
        return typed_server_message(
            "EXCHANGES_FETCHED",
            [],
            SuccessEnvelope[list[QuestionResponse], ResponseMetadata],
            "bot_exchange_history",
            headers={"Cache-Control": "no-store"},
        )
    questions = get_recent_exchanges(db, user.id, limit=limit)
    return typed_server_message(
        "EXCHANGES_FETCHED",
        [_serialize(question) for question in questions],
        SuccessEnvelope[list[QuestionResponse], ResponseMetadata],
        "bot_exchange_history",
        headers={"Cache-Control": "no-store"},
    )


@router.get(
    "/users/{pseudo_id}/search",
    response_model=SuccessEnvelope[list[QuestionResponse], ResponseMetadata],
)
def search_history(
    pseudo_id: str,
    q: str = Query(..., min_length=1),
    top_k: int = Query(3, ge=1, le=10),
    db: Session = Depends(get_db),
    _bot: bool = Depends(verify_bot_api_key),
):
    user = find_user_by_pseudo_id(db, pseudo_id)
    if not user:
        return typed_server_message(
            "EXCHANGES_FETCHED",
            [],
            SuccessEnvelope[list[QuestionResponse], ResponseMetadata],
            "bot_exchange_search",
            headers={"Cache-Control": "no-store"},
        )
    questions = search_exchanges(db, user.id, query=q, top_k=top_k)
    return typed_server_message(
        "EXCHANGES_FETCHED",
        [_serialize(question) for question in questions],
        SuccessEnvelope[list[QuestionResponse], ResponseMetadata],
        "bot_exchange_search",
        headers={"Cache-Control": "no-store"},
    )


@router.get(
    "/knowledge/search",
    response_model=SuccessEnvelope[list[KnowledgeSearchResult], ResponseMetadata],
)
def search_knowledge(
    q: str = Query(..., min_length=1, max_length=500),
    top_k: int = Query(3, ge=1, le=10),
    db: Session = Depends(get_db),
    _bot: bool = Depends(verify_bot_api_key),
):
    """The passages of the documentary base about her question.

    Nothing here is about her: the base is the same for everyone. An empty
    list is a real answer, and the bot says it does not know rather than
    filling the gap from its memory.
    """
    extracts = search_chunks(db, q, top_k=top_k)
    return typed_server_message(
        "KNOWLEDGE_SEARCHED",
        [
            KnowledgeSearchResult(
                document_id=str(item["document_id"]),
                title=item["title"],
                source=item["source"],
                source_url=item.get("source_url"),
                content=item["content"],
            )
            for item in extracts
        ],
        SuccessEnvelope[list[KnowledgeSearchResult], ResponseMetadata],
        "bot_knowledge_search",
    )


@router.get(
    "/users/{pseudo_id}/profile",
    response_model=SuccessEnvelope[BotProfileResponse, ResponseMetadata],
)
def read_bot_profile(
    pseudo_id: str,
    db: Session = Depends(get_db),
    _bot: bool = Depends(verify_bot_api_key),
):
    user = find_user_by_pseudo_id(db, pseudo_id)
    profile = BotProfileResponse.model_validate(get_bot_profile(user, pseudo_id))
    return typed_server_message(
        "BOT_PROFILE_FETCHED",
        profile,
        SuccessEnvelope[BotProfileResponse, ResponseMetadata],
        "bot_profile_get",
        headers={"Cache-Control": "no-store"},
    )


@router.put(
    "/users/{pseudo_id}/profile",
    response_model=SuccessEnvelope[BotProfileResponse, ResponseMetadata],
)
def write_bot_profile(
    pseudo_id: str,
    data: BotProfileUpdate,
    db: Session = Depends(get_db),
    _bot: bool = Depends(verify_bot_api_key),
):
    user = _bot_user(db, pseudo_id, data.telnumber)
    profile = BotProfileResponse.model_validate(
        update_bot_preferred_name(db, user, data.preferred_name)
    )
    return typed_server_message(
        "BOT_PROFILE_UPDATED",
        profile,
        SuccessEnvelope[BotProfileResponse, ResponseMetadata],
        "bot_profile_update",
        headers={"Cache-Control": "no-store"},
    )


@router.post(
    "/reminders",
    response_model=SuccessEnvelope[ReminderResponse, ResponseMetadata],
    status_code=201,
)
def create_bot_reminder(
    data: ReminderCreate,
    db: Session = Depends(get_db),
    _bot: bool = Depends(verify_bot_api_key),
):
    _check_pseudo_id(data.pseudo_id, data.telnumber)
    try:
        reminder = create_reminder(db, data, create_user=bool(data.telnumber))
    except ReminderInPastError:
        raise ServerMessageException("REMINDER_IN_PAST")
    except UserDeletedError:
        raise ServerMessageException("USER_DELETED")
    except ValueError:
        raise ServerMessageException("USER_NOT_FOUND")
    return typed_server_message(
        "REMINDER_CREATED",
        _serialize_reminder(reminder),
        SuccessEnvelope[ReminderResponse, ResponseMetadata],
        "bot_reminder_create",
        status=201,
    )


@router.get(
    "/reminders/due",
    response_model=SuccessEnvelope[list[BotClaimedReminderResponse], ResponseMetadata],
)
def list_due_reminders(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _bot: bool = Depends(verify_bot_api_key),
):
    """Claims due reminders: each call hands out different rows (status "sending")."""
    reminders = claim_due_reminders(db, limit=limit)
    context = delivery_context(db, reminders)
    data: list[BotClaimedReminderResponse] = []
    for reminder in reminders:
        user_context = context.get(reminder.pseudo_id, {})
        telnumber = user_context.get("telnumber")
        data.append(
            BotClaimedReminderResponse.model_validate(
                {
                    **_serialize_reminder(reminder).model_dump(),
                    "telnumber": telnumber,
                    "timezone": (
                        iana_zone_for_telnumber(telnumber)
                        if telnumber
                        else settings.DEFAULT_REMINDER_TIMEZONE
                    ),
                    "last_inbound_at": user_context.get("last_inbound_at"),
                }
            )
        )
    return typed_server_message(
        "REMINDERS_CLAIMED",
        data,
        SuccessEnvelope[list[BotClaimedReminderResponse], ResponseMetadata],
        "bot_reminders_claim",
        headers={"Cache-Control": "no-store"},
    )


@router.post(
    "/reminders/cancel-by-pseudo-id",
    response_model=SuccessEnvelope[list[ReminderResponse], ResponseMetadata],
)
def cancel_user_reminders(
    pseudo_id: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    _bot: bool = Depends(verify_bot_api_key),
):
    cancelled = cancel_pending_reminders(db, pseudo_id)
    return typed_server_message(
        "REMINDER_CANCELLED",
        [_serialize_reminder(reminder) for reminder in cancelled],
        SuccessEnvelope[list[ReminderResponse], ResponseMetadata],
        "bot_reminders_cancel_by_pseudo_id",
    )


@router.get(
    "/users/{pseudo_id}/reminders",
    response_model=SuccessEnvelope[list[ReminderResponse], ResponseMetadata],
)
def list_open_reminders(
    pseudo_id: str,
    limit: int = Query(10, ge=1, le=20),
    db: Session = Depends(get_db),
    _bot: bool = Depends(verify_bot_api_key),
):
    """The user's open reminders (pending/sending), soonest first.

    Unknown users get an empty list, never a 404, so the endpoint does not
    reveal whether a pseudo_id exists (same policy as the history route).
    """
    reminders = list_user_reminders(db, pseudo_id, limit=limit)
    return typed_server_message(
        "REMINDERS_FETCHED",
        [_serialize_reminder(reminder) for reminder in reminders],
        SuccessEnvelope[list[ReminderResponse], ResponseMetadata],
        "bot_user_reminders_list",
    )


@router.post(
    "/reminders/delivery-failed",
    response_model=SuccessEnvelope[ReminderDeliveryFailureResponse, ResponseMetadata],
)
def report_delivery_failure(
    data: ReminderDeliveryFailed,
    db: Session = Depends(get_db),
    _bot: bool = Depends(verify_bot_api_key),
):
    reminder = mark_reminder_undelivered(db, data.wa_message_id, data.error_code, data.error_title)
    return typed_server_message(
        "REMINDER_DELIVERY_FAILED",
        ReminderDeliveryFailureResponse(
            matched=reminder is not None,
            reminder_id=reminder.id if reminder else None,
        ),
        SuccessEnvelope[ReminderDeliveryFailureResponse, ResponseMetadata],
        "bot_reminder_delivery_failed",
    )


@router.post(
    "/reminders/{reminder_id}/sent",
    response_model=SuccessEnvelope[ReminderResponse, ResponseMetadata],
)
def send_due_reminder(
    reminder_id: uuid.UUID,
    data: ReminderSentReport | None = None,
    db: Session = Depends(get_db),
    _bot: bool = Depends(verify_bot_api_key),
):
    try:
        reminder = mark_reminder_sent(db, reminder_id, wa_message_id=data.wa_message_id if data else None)
    except ValueError:
        raise ServerMessageException("REMINDER_NOT_FOUND")
    return typed_server_message(
        "REMINDER_SENT",
        _serialize_reminder(reminder),
        SuccessEnvelope[ReminderResponse, ResponseMetadata],
        "bot_reminder_sent",
    )


@router.post(
    "/reminders/{reminder_id}/failed",
    response_model=SuccessEnvelope[ReminderResponse, ResponseMetadata],
)
def fail_due_reminder(
    reminder_id: uuid.UUID,
    data: ReminderFailedReport | None = None,
    error: str | None = Query(None, description="Deprecated, send the JSON body instead."),
    db: Session = Depends(get_db),
    _bot: bool = Depends(verify_bot_api_key),
):
    message = (data.error if data else None) or error
    try:
        reminder = mark_reminder_failed(db, reminder_id, message)
    except ValueError:
        raise ServerMessageException("REMINDER_NOT_FOUND")
    return typed_server_message(
        "REMINDER_FAILED",
        _serialize_reminder(reminder),
        SuccessEnvelope[ReminderResponse, ResponseMetadata],
        "bot_reminder_failed",
    )


@router.post(
    "/reminders/{reminder_id}/cancel",
    response_model=SuccessEnvelope[ReminderResponse, ResponseMetadata],
)
def cancel_bot_reminder(
    reminder_id: uuid.UUID,
    pseudo_id: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    _bot: bool = Depends(verify_bot_api_key),
):
    try:
        reminder = cancel_user_reminder(db, reminder_id, pseudo_id)
    except ValueError:
        raise ServerMessageException("REMINDER_NOT_FOUND")
    return typed_server_message(
        "REMINDER_CANCELLED",
        _serialize_reminder(reminder),
        SuccessEnvelope[ReminderResponse, ResponseMetadata],
        "bot_reminder_cancel",
    )


@router.post(
    "/feedback/schedule",
    response_model=SuccessEnvelope[FeedbackScheduleResponse, ResponseMetadata],
)
def schedule_feedback_question(
    data: FeedbackScheduleRequest,
    db: Session = Depends(get_db),
    _bot: bool = Depends(verify_bot_api_key),
):
    _bot_user(db, data.pseudo_id, data.telnumber)
    scheduled = schedule_feedback(db, data.pseudo_id)
    return typed_server_message(
        "FEEDBACK_SCHEDULE_CHECKED",
        FeedbackScheduleResponse(scheduled=scheduled),
        SuccessEnvelope[FeedbackScheduleResponse, ResponseMetadata],
        "bot_feedback_schedule",
    )


@router.post(
    "/feedback",
    response_model=SuccessEnvelope[FeedbackResponse, ResponseMetadata],
    status_code=201,
)
def add_feedback(
    data: FeedbackCreate,
    db: Session = Depends(get_db),
    _bot: bool = Depends(verify_bot_api_key),
):
    user = find_user_by_pseudo_id(db, data.pseudo_id)
    if not user:
        raise ServerMessageException("USER_NOT_FOUND")
    if user.deleted_at is not None:
        raise ServerMessageException("USER_DELETED")
    response = record_feedback(db, data)
    return typed_server_message(
        "FEEDBACK_RECORDED",
        FeedbackResponse.model_validate(response),
        SuccessEnvelope[FeedbackResponse, ResponseMetadata],
        "bot_feedback_create",
        status=201,
        headers={"Cache-Control": "no-store"},
    )
