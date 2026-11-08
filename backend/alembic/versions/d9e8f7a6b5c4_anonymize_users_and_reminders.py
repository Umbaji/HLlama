"""anonymize_users_and_reminders

Adds pseudo_id to users (HMAC of phone number), encrypts phone numbers at
rest, and switches reminders from raw phone numbers to pseudo_ids.

Revision ID: d9e8f7a6b5c4
Revises: c7d4a2e1b3f0
Create Date: 2026-08-11 12:00:00.000000
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from helpers.anonymity import encrypt_number, pseudo_id_for

revision: str = 'd9e8f7a6b5c4'
down_revision: Union[str, None] = 'c7d4a2e1b3f0'
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

    # --- reminders: telnumber -> pseudo_id --------------------------------
    op.add_column('reminders', sa.Column('pseudo_id', sa.String(length=64), nullable=True))

    rows = bind.execute(sa.text('SELECT id, telnumber FROM reminders')).fetchall()
    for reminder_id, telnumber in rows:
        if not telnumber:
            continue
        bind.execute(
            sa.text('UPDATE reminders SET pseudo_id = :p WHERE id = :id'),
            {"p": pseudo_id_for(telnumber), "id": reminder_id},
        )

    op.alter_column('reminders', 'pseudo_id', nullable=False)
    op.create_index('ix_reminders_pseudo_id', 'reminders', ['pseudo_id'])
    op.drop_index('ix_reminders_telnumber', table_name='reminders')
    op.drop_column('reminders', 'telnumber')


def downgrade() -> None:
    bind = op.get_bind()

    # --- reminders: restore telnumber (decrypt is lossless) ---------------
    op.add_column('reminders', sa.Column('telnumber', sa.String(length=20), nullable=True))

    from helpers.anonymity import decrypt_number
    rows = bind.execute(sa.text('SELECT id, pseudo_id FROM reminders')).fetchall()
    for reminder_id, pseudo_id in rows:
        user = bind.execute(
            sa.text('SELECT telnumber FROM users WHERE pseudo_id = :p'),
            {"p": pseudo_id},
        ).fetchone()
        if user and user[0]:
            bind.execute(
                sa.text('UPDATE reminders SET telnumber = :t WHERE id = :id'),
                {"t": decrypt_number(user[0]), "id": reminder_id},
            )

    op.create_index('ix_reminders_telnumber', 'reminders', ['telnumber'])
    op.drop_index('ix_reminders_pseudo_id', table_name='reminders')
    op.drop_column('reminders', 'pseudo_id')

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
