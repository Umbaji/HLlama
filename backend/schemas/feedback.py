import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_ANSWER_LENGTH = 500


class FeedbackScheduleRequest(BaseModel):
    pseudo_id: str = Field(min_length=1, max_length=64)
    telnumber: str = Field(min_length=7, max_length=32)


class FeedbackCreate(BaseModel):
    pseudo_id: str = Field(min_length=1, max_length=64)
    question_key: str = Field(pattern=r"^[a-z0-9_]{1,50}$")
    rating: int | None = Field(default=None, ge=1, le=5)
    answer: str | None = None

    @field_validator("answer")
    @classmethod
    def trim_answer(cls, value: str | None) -> str | None:
        # Truncated rather than rejected: a long free-text comment is still worth keeping.
        text = (value or "").strip()[:MAX_ANSWER_LENGTH]
        return text or None

    @model_validator(mode="after")
    def rating_or_answer(self) -> "FeedbackCreate":
        if self.rating is None and self.answer is None:
            raise ValueError("rating or answer is required")
        return self


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, from_attributes=True)

    id: uuid.UUID
    pseudo_id: str
    question_key: str
    rating: int | None = None
    answer: str | None = None
    created_at: datetime


class FeedbackScheduleResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    scheduled: bool
