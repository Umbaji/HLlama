import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class ConsentRecordModel(Base):
    __tablename__ = "consent_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pseudo_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    # Identifier of the link that recorded this decision. Unique, so a consent
    # link works once; NULL on rows recorded before single-use links existed.
    token_jti: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)
    # Version of the policy text the decision answered (H1). NULL on rows
    # recorded before the version was stored: that text is not known.
    policy_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
