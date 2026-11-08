"""exchange full-text index uses the french configuration

The bot recalls a subject by full-text search. The old index was built with
the "simple" configuration, which matches exact tokens only: "règles" and
"regles", "douloureuse" and "douloureuses" never matched each other, so a
rephrased follow-up came back empty and the bot seemed to forget the subject.

"french" stems and folds accents while staying a stock PostgreSQL
configuration, available on Azure Database for PostgreSQL. The application
query was switched to "french"; the index must follow, or PostgreSQL ignores
it and falls back to a sequential scan.

Revision ID: e2f8b6c4a1d9
Revises: d41a8c7b93e2
Create Date: 2026-10-02 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'e2f8b6c4a1d9'
down_revision: Union[str, None] = 'd41a8c7b93e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_questions_fts")
    op.execute(
        "CREATE INDEX ix_questions_fts ON questions "
        "USING gin (to_tsvector('french', question || ' ' || coalesce(response, '')))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_questions_fts")
    op.execute(
        "CREATE INDEX ix_questions_fts ON questions "
        "USING gin (to_tsvector('simple', question || ' ' || coalesce(response, '')))"
    )