import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ConsentSubmission(BaseModel):
    token: str
    decision: str  # "accepted" | "refused"


class ConsentResponse(BaseModel):
    id: uuid.UUID
    pseudo_id: str
    decision: str
    recorded_at: datetime

    model_config = {"from_attributes": True}


class BotConsentLookup(BaseModel):
    """Sent in the body so the phone number never lands in a URL or access log."""

    pseudo_id: str = Field(min_length=1, max_length=64)
    telnumber: str = Field(min_length=7, max_length=32)
