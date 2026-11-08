import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class HealthFactModel(Base):
    """A fact about her health, in her own words, kept only with her agreement.

    The fact is stored as she said it: the application does not parse it, does
    not interpret it, and does not turn it into a number. A fact that is wrong
    is removed, and the history of what was removed stays in the row.
    """

    __tablename__ = "health_facts"
    __table_args__ = (
        Index("ix_health_facts_pseudo_id_active", "pseudo_id", "active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    pseudo_id: Mapped[str] = mapped_column(String(64), nullable=False)
    fact: Mapped[str] = mapped_column(Text, nullable=False)
    # The agreement of the person, with the moment she gave it. A fact without
    # it is not kept.
    consented_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
