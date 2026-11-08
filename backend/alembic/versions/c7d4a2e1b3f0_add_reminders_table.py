"""add_reminders_table

Revision ID: c7d4a2e1b3f0
Revises: b3f1c2a4d5e6
Create Date: 2026-08-07 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c7d4a2e1b3f0'
down_revision: Union[str, None] = 'b3f1c2a4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'reminders',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('telnumber', sa.String(length=20), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('repeat_interval_days', sa.SmallInteger(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('attempts', sa.SmallInteger(), nullable=False, server_default='0'),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_reminders_telnumber', 'reminders', ['telnumber'])
    op.create_index('ix_reminders_scheduled_at', 'reminders', ['scheduled_at'])
    op.create_index('ix_reminders_status', 'reminders', ['status'])


def downgrade() -> None:
    op.drop_index('ix_reminders_status', table_name='reminders')
    op.drop_index('ix_reminders_scheduled_at', table_name='reminders')
    op.drop_index('ix_reminders_telnumber', table_name='reminders')
    op.drop_table('reminders')
