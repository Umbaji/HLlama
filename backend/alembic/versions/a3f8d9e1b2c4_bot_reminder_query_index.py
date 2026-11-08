"""bot reminder query index

Serves the two per-user reminder reads that back the bot's "mes rappels"
answer and its targeted cancel: the list endpoint filters pseudo_id + status
and orders by scheduled_at, and cancel_pending_reminders filters the same
leading columns. A composite index replaces the per-user scan without touching
the existing single-column indexes used by other query paths.

Revision ID: a3f8d9e1b2c4
Revises: f6d3a5b7c2e9
Create Date: 2026-10-02 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'a3f8d9e1b2c4'
down_revision: Union[str, None] = 'f6d3a5b7c2e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_reminders_pseudo_id_status_scheduled",
        "reminders",
        ["pseudo_id", "status", "scheduled_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_reminders_pseudo_id_status_scheduled", table_name="reminders")