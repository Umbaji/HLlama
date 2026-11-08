"""Record which policy text a consent decision answered (sheet H1).

A decision only proves consent to the text that was shown. Rows recorded before
this column existed keep NULL: their text version is not known.

Revision ID: c8d5e3f0b2a4
Revises: d4e7b1a93c68
Create Date: 2026-10-09 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'c8d5e3f0b2a4'
down_revision: Union[str, None] = 'd4e7b1a93c68'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE consent_records ADD COLUMN IF NOT EXISTS policy_version VARCHAR(32) NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE consent_records DROP COLUMN IF EXISTS policy_version")
