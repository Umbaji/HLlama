from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from database import get_db
from helpers.anonymity import pseudo_id_for
from helpers.server_message import (
    ServerMessageException,
    server_message,
    typed_server_message,
)
from schemas.bot_profile import BotProfileResponse, BotProfileUpdate
from schemas.common import ResponseMetadata, SuccessEnvelope
from schemas.feedback import FeedbackCreate, FeedbackResponse
from schemas.knowledge import KnowledgeSearchResult
from schemas.question import BotExchangeCreate, QuestionResponse
from services.bot_auth import verify_bot_api_key
from services.feedback_service import record_feedback
from services.knowledge import search_chunks
from services.question_service import (
    create_bot_exchange,
    get_recent_exchanges,
    search_exchanges,
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
