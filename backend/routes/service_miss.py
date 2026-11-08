"""The wordings that named a service and were not understood.

The bot can only grow its services from what she really says, and that means
recording the wordings it did not understand. The record holds the shape of a
sentence, never its content: no digits, no names, no links, and nothing of
what she wrote about her health.
"""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from helpers.server_message import ServerMessageException, server_message
from services.auth_service import get_current_active_user
from services.bot_auth import verify_bot_api_key
from services.service_miss import list_misses, record_miss

bot_router = APIRouter(prefix="/api/bot", tags=["service-misses"])
admin_router = APIRouter(prefix="/api/service-misses", tags=["service-misses"])


class ServiceMissCreate(BaseModel):
    """A wording, already scrubbed by the bot."""

    service: str | None = Field(default=None, max_length=32)
    wording: str = Field(min_length=1, max_length=200)
    language: str = Field(default="fr", max_length=8)


class ServiceMissResponse(BaseModel):
    id: uuid.UUID
    service: str | None = None
    wording: str
    language: str
    hits: int
    created_at: datetime
    last_seen_at: datetime

    model_config = {"from_attributes": True}


@bot_router.post("/service-misses")
def create_service_miss(
    data: ServiceMissCreate,
    db: Session = Depends(get_db),
    _bot: bool = Depends(verify_bot_api_key),
):
    """Records a wording the bot did not understand."""
    try:
        miss = record_miss(db, data.service, data.wording)
    except ValueError:
        raise ServerMessageException("WORDING_REQUIRED", status=400)
    return server_message(
        "SERVICE_MISS_RECORDED",
        data=ServiceMissResponse.model_validate(miss).model_dump(),
        status=201,
    )


@admin_router.get("")
def fetch_service_misses(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """The wordings, the ones that come back most often first."""
    if not current_user.is_admin:
        raise ServerMessageException("UNAUTHORIZED_ACCESS", status=403)
    rows = list_misses(db, limit=limit)
    return server_message(
        "SERVICE_MISSES_FETCHED",
        data=[
            {
                "id": str(miss.id),
                "service": miss.service,
                "wording": miss.wording,
                "language": miss.language,
                "hits": hits,
                "created_at": miss.created_at,
                "last_seen_at": miss.last_seen_at,
            }
            for miss, hits in rows
        ],
    )
