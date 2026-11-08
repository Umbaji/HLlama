"""add_response_to_questions

Revision ID: b3f1c2a4d5e6
Revises: 2896daa17ea9
Create Date: 2026-08-06 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b3f1c2a4d5e6'
down_revision: Union[str, None] = '2896daa17ea9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('questions', sa.Column('response', sa.Text(), nullable=True))
    op.add_column('questions', sa.Column('request_type', sa.String(length=50), nullable=True))
    op.execute(
        "CREATE INDEX ix_questions_fts ON questions "
        "USING gin (to_tsvector('simple', question || ' ' || coalesce(response, '')))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_questions_fts")
    op.drop_column('questions', 'request_type')
    op.drop_column('questions', 'response')
