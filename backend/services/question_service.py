import logging
import uuid

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from clients import embeddings
from config import settings
from models.question import QuestionModel

logger = logging.getLogger(__name__)


def create_question(db: Session, user_id: uuid.UUID, question: str) -> QuestionModel:
    q = QuestionModel(
        user_id=user_id,
        question=question,
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    return q


def create_bot_exchange(
    db: Session,
    user_id: uuid.UUID,
    question: str,
    response: str | None = None,
    request_type: str | None = None,
) -> QuestionModel:
    q = QuestionModel(
        user_id=user_id,
        question=question,
        response=response,
        request_type=request_type,
    )
    db.add(q)
    db.commit()
    db.refresh(q)
    return q


def get_user_questions(db: Session, user_id: uuid.UUID) -> list[QuestionModel]:
    result = db.execute(
        select(QuestionModel)
        .where(QuestionModel.user_id == user_id)
        .order_by(QuestionModel.created_at)
    )
    return list(result.scalars().all())


def get_recent_exchanges(
    db: Session, user_id: uuid.UUID, limit: int = 8
) -> list[QuestionModel]:
    result = db.execute(
        select(QuestionModel)
        .where(QuestionModel.user_id == user_id)
        .order_by(QuestionModel.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


def _fulltext_search_exchanges(
    db: Session, user_id: uuid.UUID, query: str, top_k: int
) -> list[QuestionModel]:
    """Keyword recall. Kept as the fallback when vector recall is unavailable."""
    vector = func.to_tsvector(
        "french",
        QuestionModel.question + " " + func.coalesce(QuestionModel.response, ""),
    )
    tsquery = func.websearch_to_tsquery("french", query)
    result = db.execute(
        select(QuestionModel)
        .where(QuestionModel.user_id == user_id, vector.op("@@")(tsquery))
        .order_by(func.ts_rank(vector, tsquery).desc(), QuestionModel.created_at.desc())
        .limit(top_k)
    )
    return list(result.scalars().all())


def search_exchanges(
    db: Session,
    user_id: uuid.UUID,
    query: str,
    top_k: int = 3,
) -> list[QuestionModel]:
    """Semantic-first recall of past exchanges, full-text fallback.

    When embeddings are configured, the query is embedded and rows are matched
    by cosine distance below SEMANTIC_MAX_DISTANCE. Any failure — provider not
    configured, a slow or odd answer — falls back to the keyword search below,
    so the route always answers. The vector column only exists on PostgreSQL,
    which is why the semantic branch runs raw SQL and why the fallback exists
    for SQLite tests.
    """
    if embeddings.is_configured():
        try:
            vector = embeddings.embed(query)
            matched = _vector_search_exchanges(db, user_id, vector, top_k)
            if matched:
                return matched
        except embeddings.EmbeddingsUnavailable as exc:
            logger.warning("Semantic search fell back to full-text: %s", exc)
    return _fulltext_search_exchanges(db, user_id, query, top_k)


def _vector_search_exchanges(
    db: Session, user_id: uuid.UUID, vector: list[float], top_k: int
) -> list[QuestionModel]:
    """Rows whose embedding is closer than SEMANTIC_MAX_DISTANCE, closest first."""
    literal = embeddings.vector_literal(vector)
    result = db.execute(
        text(
            "SELECT id FROM questions "
            "WHERE user_id = :user_id AND embedding IS NOT NULL "
            "AND embedding <=> CAST(:vector AS vector) < :distance "
            "ORDER BY embedding <=> CAST(:vector AS vector) ASC "
            "LIMIT :top_k"
        ),
        {
            "user_id": user_id,
            "vector": literal,
            "distance": settings.SEMANTIC_MAX_DISTANCE,
            "top_k": top_k,
        },
    )
    ids = [row["id"] for row in result.mappings().all()]
    if not ids:
        return []
    rows = db.execute(
        select(QuestionModel).where(QuestionModel.id.in_(ids))
    ).scalars().all()
    by_id = {str(item.id): item for item in rows}
    return [by_id[str(item_id)] for item_id in ids]
