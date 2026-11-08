"""add shared admin login attempt buckets

Revision ID: c2f9a7d1b4e6
Revises: c8d5e3f0b2a4
Create Date: 2026-10-29 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c2f9a7d1b4e6"
down_revision: Union[str, None] = "c8d5e3f0b2a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_users_email_lower",
        "users",
        [sa.text("lower(email)")],
        unique=False,
    )
    op.create_table(
        "login_attempt_buckets",
        sa.Column("bucket_key", sa.String(length=64), nullable=False),
        sa.Column("bucket_kind", sa.String(length=8), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("cooldown_level", sa.Integer(), nullable=False),
        sa.Column("blocked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("bucket_kind IN ('identity', 'ip')"),
        sa.CheckConstraint("attempt_count >= 0 AND attempt_count <= 31"),
        sa.CheckConstraint("cooldown_level >= 0 AND cooldown_level <= 4"),
        sa.PrimaryKeyConstraint("bucket_key"),
    )
    op.create_index(
        "ix_login_attempt_buckets_expires_at",
        "login_attempt_buckets",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_login_attempt_buckets_expires_at",
        table_name="login_attempt_buckets",
    )
    op.drop_table("login_attempt_buckets")
    op.drop_index("ix_users_email_lower", table_name="users")
