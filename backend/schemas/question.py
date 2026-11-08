import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class QuestionCreate(BaseModel):
    question: str


class BotExchangeCreate(BaseModel):
    pseudo_id: str = Field(min_length=1, max_length=64)
    telnumber: str | None = Field(default=None, max_length=32)
    question: str = Field(max_length=10_000)
    response: str | None = Field(default=None, max_length=20_000)
    request_type: str | None = Field(default=None, max_length=50)


class QuestionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, from_attributes=True)

    id: uuid.UUID
    question: str
    response: str | None = None
    request_type: str | None = None
    created_at: datetime


class QuestionRecordResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, from_attributes=True)

    id: uuid.UUID
    question: str
    response: str | None = None
    request_type: str | None = None
    created_at: datetime
