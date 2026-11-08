"""user last inbound at

When the consent gate blocks a first message, no exchange is recorded, so the
backend cannot tell that the woman wrote and the WhatsApp free-form window is
open. The consent link request is proof that she just did, and is stored here.

Revision ID: d41a8c7b93e2
Revises: c3f7a1b20d55
Create Date: 2026-09-29 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd41a8c7b93e2'
down_revision: Union[str, None] = 'c3f7a1b20d55'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('last_inbound_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'last_inbound_at')
