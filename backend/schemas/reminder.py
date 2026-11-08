import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ReminderKind = Literal[
    "cycle", "pill", "injection", "appointment", "feedback", "notice", "other"
]
ReminderStatus = Literal[
    "pending", "sending", "sent", "failed", "undelivered", "cancelled"
]


class ReminderCreate(BaseModel):
    pseudo_id: str = Field(min_length=1, max_length=64)
    telnumber: str | None = Field(default=None, max_length=32)
    kind: ReminderKind = "other"
    message: str = Field(min_length=1, max_length=1000)
    scheduled_at: datetime
    repeat_interval_days: int | None = Field(default=None, ge=1, le=365)


class ReminderSentReport(BaseModel):
    wa_message_id: str | None = Field(default=None, max_length=128)


class ReminderFailedReport(BaseModel):
    # No max_length: the server truncates, a long provider error must never 422.
    error: str | None = None


class ReminderDeliveryFailed(BaseModel):
    wa_message_id: str = Field(min_length=1, max_length=128)
    error_code: int | None = None
    error_title: str | None = None


class ReminderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, from_attributes=True)

    id: uuid.UUID
    pseudo_id: str
    kind: ReminderKind
    message: str
    scheduled_at: datetime
    repeat_interval_days: int | None = None
    status: ReminderStatus
    attempts: int
    last_error: str | None = None
    wa_message_id: str | None = None
    sent_at: datetime | None = None
    created_at: datetime


class BotClaimedReminderResponse(ReminderResponse):
    telnumber: str | None = Field(max_length=32)
    timezone: str = Field(min_length=1, max_length=64)
    last_inbound_at: datetime | None


class ReminderDeliveryFailureResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    matched: bool
    reminder_id: uuid.UUID | None
