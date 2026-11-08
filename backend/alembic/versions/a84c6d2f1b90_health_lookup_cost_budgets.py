"""add shared health lookup cost budgets

Revision ID: a84c6d2f1b90
Revises: f8b3c2d1a607
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a84c6d2f1b90"
down_revision: Union[str, None] = "f8b3c2d1a607"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "health_lookup_buckets",
        sa.Column("bucket_key", sa.String(length=64), nullable=False),
        sa.Column("operation", sa.String(length=16), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("bucket_key"),
        sa.CheckConstraint(
            "operation IN ('nearest', 'geocode')",
            name="ck_health_lookup_operation",
        ),
        sa.CheckConstraint("request_count >= 0", name="ck_health_lookup_count"),
    )
    op.create_index(
        "ix_health_lookup_buckets_expires_at",
        "health_lookup_buckets",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_health_lookup_buckets_expires_at",
        table_name="health_lookup_buckets",
    )
    op.drop_table("health_lookup_buckets")
