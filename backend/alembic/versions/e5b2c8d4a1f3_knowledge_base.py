"""the documentary base: documents and their passages

The model answered from what it remembered and invented figures: dosages,
prices, durations. The base gives it passages it may quote, and nothing else.

The tables live here and in the models; the embedding column is created only
here, in the database: the vector type does not exist on SQLite, where the test
suite runs, so the SQLAlchemy model deliberately stays unaware of it and the
search service uses raw SQL fragments, like the recall over the exchanges.

Revision ID: e5b2c8d4a1f3
Revises: c8a1d4e7f2b9
Create Date: 2026-10-21 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "e5b2c8d4a1f3"
down_revision: Union[str, None] = "a3f8d9e1b2c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "knowledge_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(length=120), nullable=False, unique=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("language", sa.String(length=8), nullable=False, server_default="fr"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "document_id", "ordinal", name="uq_knowledge_chunks_document_ordinal"
        ),
    )
    op.create_index(
        "ix_knowledge_chunks_document_id", "knowledge_chunks", ["document_id"]
    )
    # The French configuration of the questions index applies here too: "règles"
    # and "regles" must match each other.
    op.execute(
        "CREATE INDEX ix_knowledge_chunks_fts ON knowledge_chunks "
        "USING gin (to_tsvector('french', content))"
    )
    # Azure Database for PostgreSQL refuses CREATE EXTENSION to anyone outside
    # azure_pg_admin, so the extension is only created here when missing.
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') "
        "THEN CREATE EXTENSION vector; END IF; "
        "END $$"
    )
    op.execute("ALTER TABLE knowledge_chunks ADD COLUMN embedding vector(1536) NULL")
    op.execute(
        "CREATE INDEX ix_knowledge_chunks_embedding_hnsw "
        "ON knowledge_chunks USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_embedding_hnsw")
    op.execute("ALTER TABLE knowledge_chunks DROP COLUMN IF EXISTS embedding")
    op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_fts")
    op.drop_index("ix_knowledge_chunks_document_id", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_documents")
