"""anonymize_users

Adds pseudo_id to users (HMAC of phone number) and encrypts phone numbers at
rest.

Revision ID: d9e8f7a6b5c4
Revises: b3f1c2a4d5e6
Create Date: 2026-08-11 12:00:00.000000
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from helpers.anonymity import encrypt_number, pseudo_id_for

revision: str = 'd9e8f7a6b5c4'
down_revision: Union[str, None] = 'b3f1c2a4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # --- users: add pseudo_id, backfill, encrypt telnumber -----------------
    op.add_column('users', sa.Column('pseudo_id', sa.String(length=64), nullable=True))
    op.alter_column('users', 'telnumber', type_=sa.String(length=512))

    rows = bind.execute(sa.text('SELECT id, telnumber FROM users')).fetchall()
    for user_id, telnumber in rows:
        if telnumber:
            pseudo_id = pseudo_id_for(telnumber)
            encrypted = encrypt_number(telnumber)
        else:
            pseudo_id = uuid.uuid4().hex
            encrypted = None
        bind.execute(
            sa.text('UPDATE users SET pseudo_id = :p, telnumber = :t WHERE id = :id'),
            {"p": pseudo_id, "t": encrypted, "id": user_id},
        )

    op.alter_column('users', 'pseudo_id', nullable=False)
    op.create_index('ix_users_pseudo_id', 'users', ['pseudo_id'], unique=True)

    # telnumber is now opaque (encrypted), so the unique constraint goes away
    try:
        op.drop_constraint('users_telnumber_key', 'users', type_='unique')
    except Exception:
        pass


def downgrade() -> None:
    bind = op.get_bind()

    # --- users: restore plaintext telnumber, drop pseudo_id ---------------
    rows = bind.execute(sa.text('SELECT id, telnumber FROM users')).fetchall()
    from helpers.anonymity import decrypt_number as _dec
    for user_id, telnumber in rows:
        if telnumber:
            bind.execute(
                sa.text('UPDATE users SET telnumber = :t WHERE id = :id'),
                {"t": _dec(telnumber), "id": user_id},
            )

    op.drop_index('ix_users_pseudo_id', table_name='users')
    op.drop_column('users', 'pseudo_id')
    try:
        op.create_unique_constraint('users_telnumber_key', 'users', ['telnumber'])
    except Exception:
        pass
