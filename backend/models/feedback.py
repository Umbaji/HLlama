import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, SmallInteger, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class FeedbackResponseModel(Base):
    __tablename__ = "feedback_responses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pseudo_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    question_key: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    rating: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    answer: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True
    )
