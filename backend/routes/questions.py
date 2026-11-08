from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from helpers.server_message import ServerMessageException, typed_server_message
from schemas.common import ResponseMetadata, SuccessEnvelope
from schemas.question import QuestionCreate, QuestionRecordResponse
from services.bot_auth import verify_bot_api_key
from services.question_service import create_question, get_user_questions
from services.user_service import find_user_by_pseudo_id

router = APIRouter(prefix="/api/users", tags=["questions"])


@router.post(
    "/{pseudo_id}/questions",
    response_model=SuccessEnvelope[QuestionRecordResponse, ResponseMetadata],
    status_code=201,
)
def add_question(
    pseudo_id: str,
    data: QuestionCreate,
    db: Session = Depends(get_db),
    _bot: bool = Depends(verify_bot_api_key),
):
    user = find_user_by_pseudo_id(db, pseudo_id)
    if not user:
        raise ServerMessageException("USER_NOT_FOUND")
    question = create_question(db, user.id, data.question)
    return typed_server_message(
        "QUESTION_CREATED",
        QuestionRecordResponse.model_validate(question),
        SuccessEnvelope[QuestionRecordResponse, ResponseMetadata],
        "user_questions_create",
        status=201,
    )


@router.get(
    "/{pseudo_id}/questions",
    response_model=SuccessEnvelope[list[QuestionRecordResponse], ResponseMetadata],
)
def list_questions(
    pseudo_id: str,
    db: Session = Depends(get_db),
    _bot: bool = Depends(verify_bot_api_key),
):
    user = find_user_by_pseudo_id(db, pseudo_id)
    if not user:
        raise ServerMessageException("USER_NOT_FOUND")
    questions = get_user_questions(db, user.id)
    return typed_server_message(
        "QUESTIONS_FETCHED",
        [QuestionRecordResponse.model_validate(question) for question in questions],
        SuccessEnvelope[list[QuestionRecordResponse], ResponseMetadata],
        "user_questions_list",
    )
