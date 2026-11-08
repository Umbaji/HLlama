"""the facts she declared about her health

A fact is kept only with her agreement, and a fact she got wrong can be
removed. The fact is stored as she said it.

Revision ID: d4e7b1a93c68
Revises: c7d1a4e9b350
Create Date: 2026-10-21 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "d4e7b1a93c68"
down_revision: Union[str, None] = "c7d1a4e9b350"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "health_facts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("pseudo_id", sa.String(length=64), nullable=False),
        sa.Column("fact", sa.Text(), nullable=False),
        # The agreement of the person, with the moment she gave it: a fact
        # without it is not kept.
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_health_facts_pseudo_id_active", "health_facts", ["pseudo_id", "active"]
    )


def downgrade() -> None:
    op.drop_index("ix_health_facts_pseudo_id_active", table_name="health_facts")
    op.drop_table("health_facts")
