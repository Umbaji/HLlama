from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class LoginAttemptBucketModel(Base):
    __tablename__ = "login_attempt_buckets"
    __table_args__ = (
        CheckConstraint("bucket_kind IN ('identity', 'ip')"),
        CheckConstraint("attempt_count >= 0 AND attempt_count <= 31"),
        CheckConstraint("cooldown_level >= 0 AND cooldown_level <= 4"),
        Index("ix_login_attempt_buckets_expires_at", "expires_at"),
    )

    bucket_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    bucket_kind: Mapped[str] = mapped_column(String(8), nullable=False)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cooldown_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
