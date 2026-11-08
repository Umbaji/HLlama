import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ServiceMissModel(Base):
    """A wording that named a service and was not understood.

    The wording is scrubbed before it arrives here: no digits, no names, no
    links. The point is to learn the words she uses for a service, not to keep
    what she wrote.
    """

    __tablename__ = "service_misses"
    __table_args__ = (
        Index("ix_service_misses_created_at", "created_at"),
        Index("ix_service_misses_service", "service"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # The service the wording seemed to name, null when it named none.
    service: Mapped[str | None] = mapped_column(String(32), nullable=True)
    wording: Mapped[str] = mapped_column(String(200), nullable=False)
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="fr", server_default="fr")
    hits: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
