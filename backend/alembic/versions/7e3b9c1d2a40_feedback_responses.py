"""feedback_responses

Revision ID: 7e3b9c1d2a40
Revises: 0d13de125418
Create Date: 2026-09-24 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '7e3b9c1d2a40'
down_revision: Union[str, None] = '0d13de125418'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'feedback_responses',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('pseudo_id', sa.String(length=64), nullable=False),
        sa.Column('question_key', sa.String(length=50), nullable=False),
        sa.Column('rating', sa.SmallInteger(), nullable=True),
        sa.Column('answer', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_feedback_responses_pseudo_id', 'feedback_responses', ['pseudo_id'])
    op.create_index('ix_feedback_responses_question_key', 'feedback_responses', ['question_key'])
    op.create_index('ix_feedback_responses_created_at', 'feedback_responses', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_feedback_responses_created_at', table_name='feedback_responses')
    op.drop_index('ix_feedback_responses_question_key', table_name='feedback_responses')
    op.drop_index('ix_feedback_responses_pseudo_id', table_name='feedback_responses')
    op.drop_table('feedback_responses')
