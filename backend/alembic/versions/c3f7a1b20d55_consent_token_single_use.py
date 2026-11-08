"""consent token single use

A consent link may record one decision and no more. The token carries a `jti`,
and the unique index makes the database itself refuse a second record for the
same token, so two taps on the same link cannot race past a check.

Existing rows predate the claim and keep a NULL jti, which the unique index
allows in both PostgreSQL and SQLite.

Revision ID: c3f7a1b20d55
Revises: 7c2e5a9d1f40
Create Date: 2026-09-29 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3f7a1b20d55'
down_revision: Union[str, None] = '7e3b9c1d2a40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('consent_records', sa.Column('token_jti', sa.String(length=64), nullable=True))
    op.create_index('ix_consent_records_token_jti', 'consent_records', ['token_jti'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_consent_records_token_jti', table_name='consent_records')
    op.drop_column('consent_records', 'token_jti')
