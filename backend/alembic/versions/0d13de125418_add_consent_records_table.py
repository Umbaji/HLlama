"""add_consent_records_table

Revision ID: 0d13de125418
Revises: b8c9d0e1f2a3
Create Date: 2026-09-24 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0d13de125418'
down_revision: Union[str, None] = 'a6c1d9e4f2b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'consent_records',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('pseudo_id', sa.String(length=64), nullable=False),
        sa.Column('decision', sa.String(length=20), nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_consent_records_pseudo_id', 'consent_records', ['pseudo_id'])


def downgrade() -> None:
    op.drop_index('ix_consent_records_pseudo_id', table_name='consent_records')
    op.drop_table('consent_records')
