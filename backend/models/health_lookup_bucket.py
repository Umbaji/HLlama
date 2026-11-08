from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class HealthLookupBucketModel(Base):
    __tablename__ = "health_lookup_buckets"
    __table_args__ = (
        CheckConstraint(
            "operation IN ('nearest', 'geocode')",
            name="ck_health_lookup_operation",
        ),
        CheckConstraint("request_count >= 0", name="ck_health_lookup_count"),
        Index("ix_health_lookup_buckets_expires_at", "expires_at"),
    )

    bucket_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
