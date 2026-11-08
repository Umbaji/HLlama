"""fix_telnumber_column_size

The telnumber column was created as VARCHAR(20) for plaintext numbers.
Fernet-encrypted tokens are ~200 chars, causing silent truncation or errors.
This migration widens the column to VARCHAR(512) to match the SQLAlchemy model.

Revision ID: a1b2c3d4e5f6
Revises: d9e8f7a6b5c4
Create Date: 2026-08-17 17:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'd9e8f7a6b5c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('users', 'telnumber', type_=sa.String(length=512))


def downgrade() -> None:
    op.alter_column('users', 'telnumber', type_=sa.String(length=20))
