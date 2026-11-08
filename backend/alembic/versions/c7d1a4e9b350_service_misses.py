"""the wordings that named a service and were not understood

The services of the bot can only grow from what she really says, so the
wordings it did not understand are recorded - scrubbed, and never about her
health.

Revision ID: c7d1a4e9b350
Revises: b8e4d2f6a903
Create Date: 2026-10-21 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "c7d1a4e9b350"
down_revision: Union[str, None] = "e5b2c8d4a1f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "service_misses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("service", sa.String(length=32), nullable=True),
        sa.Column("wording", sa.String(length=200), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False, server_default="fr"),
        sa.Column("hits", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_service_misses_created_at", "service_misses", ["created_at"])
    op.create_index("ix_service_misses_service", "service_misses", ["service"])


def downgrade() -> None:
    op.drop_index("ix_service_misses_service", table_name="service_misses")
    op.drop_index("ix_service_misses_created_at", table_name="service_misses")
    op.drop_table("service_misses")
