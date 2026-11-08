import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Index, SmallInteger, String, column, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class UserModel(Base):
    __tablename__ = "users"
    __table_args__ = (Index("ix_users_email_lower", func.lower(column("email"))),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fullname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    preferred_name_encrypted: Mapped[str | None] = mapped_column(String(512), nullable=True)
    pseudo_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    telnumber: Mapped[str | None] = mapped_column(String(512), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    age: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Last inbound WhatsApp message, when no exchange was recorded for it
    # (a message the consent gate blocked). Feeds the 24h window.
    last_inbound_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
