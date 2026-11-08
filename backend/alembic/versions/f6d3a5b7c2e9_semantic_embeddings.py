"""semantic embeddings for exchange recall

Adds pgvector to the questions table so past exchanges can be recalled by
meaning rather than shared tokens. The column is created only here, in the
database: the vector type does not exist on SQLite, where the test suite runs,
so the SQLAlchemy model deliberately stays unaware of it and the vector
queries in the search service use raw SQL fragments.

Revision ID: f6d3a5b7c2e9
Revises: e2f8b6c4a1d9
Create Date: 2026-10-02 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'f6d3a5b7c2e9'
down_revision: Union[str, None] = 'e2f8b6c4a1d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Some managed PostgreSQL services refuse CREATE EXTENSION, even with
    # IF NOT EXISTS and an extension already there, to anyone outside their
    # administrator role. The extension is therefore only created here when
    # missing, and the deployer may need to provision it beforehand.
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') "
        "THEN CREATE EXTENSION vector; END IF; "
        "END $$"
    )
    op.execute("ALTER TABLE questions ADD COLUMN embedding vector(1536) NULL")
    op.execute(
        "CREATE INDEX ix_questions_embedding_hnsw "
        "ON questions USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_questions_embedding_hnsw")
    op.execute("ALTER TABLE questions DROP COLUMN IF EXISTS embedding")