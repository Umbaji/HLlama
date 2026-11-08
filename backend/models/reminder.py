import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


REMINDER_KINDS = ("cycle", "pill", "injection", "appointment", "feedback", "notice", "other")
# pending -> sending (claimed by a bot poll) -> sent | failed; sent -> undelivered
# when WhatsApp reports the delivery failed afterwards.
REMINDER_STATUSES = ("pending", "sending", "sent", "failed", "undelivered", "cancelled")


class ReminderModel(Base):
    __tablename__ = "reminders"
    __table_args__ = (Index("ix_reminders_pseudo_id_kind", "pseudo_id", "kind"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pseudo_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="other", server_default="other")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    repeat_interval_days: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    wa_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
