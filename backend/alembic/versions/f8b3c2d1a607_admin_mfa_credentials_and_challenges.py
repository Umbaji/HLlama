"""add admin MFA credentials, one-use challenges, and recovery codes

Revision ID: f8b3c2d1a607
Revises: c2f9a7d1b4e6
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f8b3c2d1a607"
down_revision: Union[str, None] = "c2f9a7d1b4e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "admin_mfa_credentials",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("encrypted_secret", sa.String(length=256), nullable=False),
        sa.Column("key_version", sa.Integer(), nullable=False),
        sa.Column("last_totp_counter", sa.BigInteger(), nullable=True),
        sa.Column("enabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "admin_mfa_challenges",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(length=8), nullable=False),
        sa.Column("token_digest", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("purpose IN ('setup', 'enroll', 'verify')"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_digest"),
    )
    op.create_index(
        "ix_admin_mfa_challenges_user_expiry",
        "admin_mfa_challenges",
        ["user_id", "expires_at"],
    )
    op.create_index(
        "ix_admin_mfa_challenges_expires_at",
        "admin_mfa_challenges",
        ["expires_at"],
    )
    op.create_table(
        "admin_mfa_recovery_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("code_digest", sa.String(length=64), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code_digest"),
    )
    op.create_index(
        "ix_admin_mfa_recovery_user", "admin_mfa_recovery_codes", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_admin_mfa_recovery_user", table_name="admin_mfa_recovery_codes")
    op.drop_table("admin_mfa_recovery_codes")
    op.drop_index("ix_admin_mfa_challenges_expires_at", table_name="admin_mfa_challenges")
    op.drop_index("ix_admin_mfa_challenges_user_expiry", table_name="admin_mfa_challenges")
    op.drop_table("admin_mfa_challenges")
    op.drop_table("admin_mfa_credentials")
