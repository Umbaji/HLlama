import logging
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel, ValidationError

from fastapi.encoders import jsonable_encoder
from starlette.responses import JSONResponse
from schemas.common import (
    MetadataT,
    ResponseMetadata as ResponseMetadataModel,
    ServerMessage,
    SuccessEnvelope,
)


STATUS_CODES = {
    200: [
        "SUCCESS",
        "API_HEALTH_OK",
        "USERS_FETCHED",
        "ADMINS_FETCHED",
        "USER_FETCHED",
        "ADMIN_FETCHED",
        "USER_UPDATED",
        "QUESTIONS_FETCHED",
        "NEAREST_PLACE_FOUND",
        "LOGIN_SUCCESS",
        "CURRENT_USER_FETCHED",
        "NO_CHANGE",
        "EXCHANGES_FETCHED",
        "GEOCODE_SUCCESS",
        "REMINDERS_FETCHED",
        "REMINDER_SENT",
        "REMINDER_FAILED",
        "REMINDER_CANCELLED",
        "MONITORING_HEALTH",
        "MONITORING_HISTORY",
        "BOT_PROFILE_FETCHED",
        "BOT_PROFILE_UPDATED",
        "CONSENT_RECORDED",
        "CONSENT_FETCHED",
        "CONSENT_STATUS_FETCHED",
        "CONSENT_LINK_ISSUED",
        "REMINDERS_CLAIMED",
        "REMINDER_DELIVERY_FAILED",
        "FEEDBACK_SCHEDULE_CHECKED",
        "FEEDBACK_FETCHED",
        "KNOWLEDGE_DOCUMENTS_FETCHED",
        "KNOWLEDGE_SEARCHED",
        "KNOWLEDGE_CORPUS_FETCHED",
        "KNOWLEDGE_CORPUS_SCANNED",
        "KNOWLEDGE_CORPUS_APPLIED",
        "SERVICE_MISSES_FETCHED",
        "HEALTH_FACTS_FETCHED",
        "HEALTH_FACT_REMOVED",
        "MFA_REQUIRED",
        "MFA_SETUP_REQUIRED",
        "MFA_SETUP_READY",
        "MFA_ENROLLED",
    ],
    201: [
        "USER_CREATED",
        "ADMIN_CREATED",
        "QUESTION_CREATED",
        "EXCHANGE_CREATED",
        "REMINDER_CREATED",
        "FEEDBACK_RECORDED",
        "KNOWLEDGE_DOCUMENT_INGESTED",
        "SERVICE_MISS_RECORDED",
        "HEALTH_FACT_RECORDED",
    ],
    400: [
        "BAD_REQUEST",
        "REQUIRED_FIELDS_MISSING",
        "INVALID_PLACE_CATEGORY",
        "NO_UPDATE_DATA",
        "INACTIVE_USER",
        "REMINDER_IN_PAST",
        "CONSENT_TOKEN_INVALID",
        "PSEUDO_ID_MISMATCH",
        "WORDING_REQUIRED",
        "FACT_REQUIRED",
    ],
    401: [
        "UNAUTHORIZED_ACCESS",
        "INVALID_CREDENTIALS",
        "TOKEN_INVALID",
        "MFA_INVALID",
        "MFA_CHALLENGE_EXPIRED",
        "MFA_RECOVERY_CODE_INVALID",
    ],
    403: [
        "FORBIDDEN",
        "UNAUTHORIZED_ACCESS",
        "INACTIVE_USER",
        "USER_DELETED",
        "CONSENT_REQUIRED",
    ],
    404: [
        "USER_NOT_FOUND",
        "ADMIN_NOT_FOUND",
        "NEAREST_PLACE_NOT_FOUND",
        "RESOURCE_NOT_FOUND",
        "REMINDER_NOT_FOUND",
        "CONSENT_NOT_FOUND",
        "HEALTH_FACT_NOT_FOUND",
        "KNOWLEDGE_DOCUMENT_NOT_FOUND",
        "CORPUS_CONTENT_REQUIRED",
    ],
    405: ["METHOD_NOT_ALLOWED"],
    409: [
        "CONSENT_TOKEN_ALREADY_USED",
        "EMAIL_ALREADY_EXISTS",
        "TELNUMBER_ALREADY_EXISTS",
    ],
    422: [
        "VALIDATION_ERROR",
    ],
    429: [
        "TOO_MANY_REQUESTS",
        "LOGIN_RATE_LIMITED",
    ],
    500: [
        "SERVER_ERROR",
        "UNKNOWN_ERROR",
    ],
    502: [
        "GOOGLE_MAPS_API_ERROR",
    ],
    503: [
        "LOGIN_THROTTLE_UNAVAILABLE",
        "HEALTH_LOOKUP_UNAVAILABLE",
        "MFA_UNAVAILABLE",
    ],
}
logger = logging.getLogger(__name__)

type JSONData = (
    str
    | int
    | float
    | bool
    | None
    | UUID
    | datetime
    | Decimal
    | Enum
    | BaseModel
    | list[JSONData]
    | dict[str, JSONData]
)
type JSONObject = dict[str, JSONData]
T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ResponseMetadata:
    request_id: UUID
    served_at: datetime


_response_metadata: ContextVar[ResponseMetadata | None] = ContextVar(
    "response_metadata",
    default=None,
)


def set_response_metadata(metadata: ResponseMetadata) -> Token[ResponseMetadata | None]:
    return _response_metadata.set(metadata)


def reset_response_metadata(token: Token[ResponseMetadata | None]) -> None:
    _response_metadata.reset(token)


def current_response_metadata() -> ResponseMetadata:
    metadata = _response_metadata.get()
    if metadata is not None:
        return metadata
    return ResponseMetadata(request_id=uuid4(), served_at=datetime.now(timezone.utc))


def resolve_status(message: str) -> int:
    for status, messages in STATUS_CODES.items():
        if message in messages:
            return status
    return 500


def _is_registered_for_status(message: str, status: int) -> bool:
    return message in STATUS_CODES.get(status, [])


def response_payload(
    message: str,
    data: JSONData = None,
    meta: JSONObject | None = None,
    status: int | None = None,
) -> ServerMessage:
    resolved_status = status if status is not None else resolve_status(message)
    resolved_message = message
    if not _is_registered_for_status(message, resolved_status):
        resolved_status = 500
        resolved_message = "UNKNOWN_ERROR"
    request_metadata = current_response_metadata()
    encoded_meta = jsonable_encoder(meta or {})
    if resolved_status >= 400:
        encoded_meta = {
            key: value
            for key, value in encoded_meta.items()
            if key in {
                "reason",
                "violations",
                "errors",
                "retry_after_ms",
                "retryable",
                "min",
                "max",
                "daily_max",
                "remaining",
            }
        }
    response_meta = ResponseMetadataModel.model_validate(
        {
            **encoded_meta,
            "request_id": request_metadata.request_id,
            "served_at": request_metadata.served_at,
        }
    )

    return ServerMessage(
        status=resolved_status,
        error=resolved_status >= 400,
        message=resolved_message,
        data=jsonable_encoder(None if resolved_status >= 400 else data),
        meta=response_meta,
    )


def server_message(
    message: str,
    data: JSONData = None,
    meta: JSONObject | None = None,
    status: int | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    payload = response_payload(message=message, data=data, meta=meta, status=status)
    return JSONResponse(
        status_code=payload.status,
        content=payload.model_dump(mode="json"),
        headers=headers,
    )


def typed_server_message(
    message: str,
    data: T,
    response_model: type[SuccessEnvelope[T, MetadataT]],
    operation_id: str,
    meta: JSONObject | None = None,
    status: int | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    payload = response_payload(message=message, data=data, meta=meta, status=status)
    if payload.error:
        return server_message(payload.message, status=payload.status, headers=headers)
    try:
        validated = response_model.model_validate(
            {
                "status": payload.status,
                "error": False,
                "message": payload.message,
                "data": data,
                "meta": payload.meta.model_dump(mode="python"),
            }
        )
    except ValidationError as error:
        logger.error(
            "Response contract validation failed",
            extra={
                "request_id": str(payload.meta.request_id),
                "operation_id": operation_id,
                "exception_class": type(error).__name__,
            },
        )
        return server_message("SERVER_ERROR", status=500)
    return JSONResponse(
        status_code=validated.status,
        content=validated.model_dump(mode="json"),
        headers=headers,
    )


class ServerMessageException(Exception):
    def __init__(
        self,
        message: str,
        data: JSONData = None,
        meta: JSONObject | None = None,
        status: int | None = None,
        headers: dict[str, str] | None = None,
    ):
        self.message = message
        self.data = data
        self.meta = meta
        self.status = status
        self.headers = headers
