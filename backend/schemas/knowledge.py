import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeDocumentCreate(BaseModel):
    """A document to ingest into the documentary base."""

    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=200_000)
    source: str = Field(min_length=1, max_length=120)
    source_url: str | None = Field(default=None, max_length=500)
    language: str = Field(default="fr", min_length=2, max_length=8)
    published_at: datetime | None = None


class KnowledgeDocumentResponse(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    source: str
    source_url: str | None = None
    language: str
    published_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeExtract(BaseModel):
    """One extract of the base, as the bot receives it."""

    document_id: uuid.UUID
    title: str
    source: str
    source_url: str | None = None
    content: str


class KnowledgeSearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    document_id: str
    title: str
    source: str
    source_url: str | None
    content: str
