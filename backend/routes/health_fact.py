"""What she declared about her health, kept only with her agreement.

The bot reads the facts here to answer with them, and writes here when she
declares something new. Every route is scoped by her pseudo_id: a fact of
somebody else does not exist in these endpoints.
"""
import uuid

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from helpers.server_message import ServerMessageException, server_message
from services.bot_auth import verify_bot_api_key
from services.health_fact import (
    FactNotFound,
    list_facts,
    record_fact,
    remove_fact,
    serialize,
)
from services.user_service import find_user_by_pseudo_id

router = APIRouter(prefix="/api/bot", tags=["health-facts"])


class HealthFactCreate(BaseModel):
    pseudo_id: str = Field(min_length=1, max_length=64)
    fact: str = Field(min_length=1, max_length=300)


class HealthFactResponse(BaseModel):
    id: uuid.UUID
    fact: str
    consented_at: object
    created_at: object

    model_config = {"from_attributes": True}


@router.get("/users/{pseudo_id}/health-facts")
def fetch_health_facts(
    pseudo_id: str,
    db: Session = Depends(get_db),
    _bot: bool = Depends(verify_bot_api_key),
):
    """The facts she declared, the most recent first."""
    facts = list_facts(db, pseudo_id)
    return server_message(
        "HEALTH_FACTS_FETCHED",
        data=[serialize(fact) for fact in facts],
    )


@router.post("/health-facts")
def create_health_fact(
    data: HealthFactCreate,
    db: Session = Depends(get_db),
    _bot: bool = Depends(verify_bot_api_key),
):
    """Keeps a fact she declared, with the moment she agreed to it."""
    user = find_user_by_pseudo_id(db, data.pseudo_id)
    if not user:
        raise ServerMessageException("USER_NOT_FOUND", status=404)
    try:
        fact = record_fact(db, data.pseudo_id, user.id, data.fact)
    except ValueError:
        raise ServerMessageException("FACT_REQUIRED", status=400)
    return server_message(
        "HEALTH_FACT_RECORDED",
        data=serialize(fact),
        status=201,
    )


@router.post("/health-facts/{fact_id}/remove")
def delete_health_fact(
    fact_id: uuid.UUID,
    pseudo_id: str = Query(..., min_length=1, max_length=64),
    db: Session = Depends(get_db),
    _bot: bool = Depends(verify_bot_api_key),
):
    """Removes one of her facts: a fact she got wrong must be correctable."""
    try:
        fact = remove_fact(db, fact_id, pseudo_id)
    except FactNotFound:
        raise ServerMessageException("HEALTH_FACT_NOT_FOUND", status=404)
    return server_message("HEALTH_FACT_REMOVED", data=serialize(fact))
