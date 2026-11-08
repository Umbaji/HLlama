"""The documentary base: WHO, UNFPA, national protocols.

The model used to answer from what it remembered, and it invented figures:
dosages, prices, durations, statistics. The base gives it extracts it may
quote, and nothing else.

The search has the same shape as the one over her exchanges: semantic first,
full-text fallback, French configuration so "règles" and "regles" match each
other. The distance is tighter: a passage that is not really about her question
is worse than no passage, because the model may quote it.
"""
import logging
import re
import unicodedata
from datetime import datetime

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from clients import embeddings
from config import settings
from models.knowledge import KnowledgeChunkModel, KnowledgeDocumentModel

LOGGER = logging.getLogger(__name__)

# A chunk is a passage, not a page: long enough to carry a figure with the
# context that gives it a meaning, short enough to be read in the prompt.
CHUNK_MAX_CHARS = 1200
CHUNK_MIN_CHARS = 120
_STOP_WORDS = {
    "comment", "combien", "pourquoi", "quelle", "quels", "quand",
    "avec", "sans", "elle", "vous", "nous", "cette", "dans", "pour",
    "les", "des", "une", "sur", "plus", "tout", "leur", "cela", "sont",
}
MAX_CHUNKS_PER_DOCUMENT = 400

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def slugify(title: str) -> str:
    """A stable identifier for a document, from its title."""
    decomposed = unicodedata.normalize("NFKD", title or "")
    ascii_value = "".join(char for char in decomposed if not unicodedata.combining(char))
    slug = _SLUG_STRIP.sub("-", ascii_value.lower()).strip("-")
    return slug[:120] or "document"


def _split_long(text: str, max_chars: int) -> list[str]:
    """Cuts a paragraph too long to be a chunk, on sentence boundaries."""
    pieces: list[str] = []
    current = ""
    for sentence in _SENTENCE_END.split(text):
        while len(sentence) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            pieces.append(sentence[:max_chars])
            sentence = sentence[max_chars:]
        if not current:
            current = sentence
        elif len(current) + 1 + len(sentence) <= max_chars:
            current = f"{current} {sentence}"
        else:
            pieces.append(current)
            current = sentence
    if current:
        pieces.append(current)
    return pieces


def chunk_text(content: str, max_chars: int = CHUNK_MAX_CHARS) -> list[str]:
    """The passages of a document.

    Paragraphs are the natural boundary: a figure and the sentence that gives
    it a meaning belong together. A paragraph too long is cut on sentences. A
    paragraph too short is joined to the next one: a document made of short
    paragraphs is still a document, and a fragment on its own carries nothing.
    """
    paragraphs = [block.strip() for block in re.split(r"\n\s*\n", content or "") if block.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        pieces = (
            [paragraph]
            if len(paragraph) <= max_chars
            else _split_long(paragraph, max_chars)
        )
        for piece in pieces:
            if not current:
                current = piece
            elif len(current) + 1 + len(piece) <= max_chars:
                current = f"{current}\n\n{piece}"
            else:
                chunks.append(current)
                current = piece
    if current:
        chunks.append(current)
    return chunks


def _embed_chunks(db: Session, chunks: list[KnowledgeChunkModel]) -> None:
    """Writes the embedding of each chunk, when the database has the column.

    The column only exists on PostgreSQL: the suite runs on SQLite, where a
    vector type does not exist, so the write is skipped there and the search
    falls back to full-text.
    """
    if not embeddings.is_configured():
        return
    if db.bind is None or db.bind.dialect.name != "postgresql":
        return
    for chunk in chunks:
        try:
            vector = embeddings.embed(chunk.content)
            db.execute(
                text(
                    "UPDATE knowledge_chunks SET embedding = CAST(:vec AS vector) "
                    "WHERE id = :id"
                ),
                {"vec": embeddings.vector_literal(vector), "id": chunk.id},
            )
        except embeddings.EmbeddingsUnavailable as exc:
            LOGGER.warning("Knowledge embedding failed: %s", type(exc).__name__)
            return


def ingest_document(
    db: Session,
    title: str,
    content: str,
    source: str,
    source_url: str | None = None,
    language: str = "fr",
    published_at: datetime | None = None,
) -> tuple[KnowledgeDocumentModel, int]:
    """Stores a document and its passages, replacing the previous version.

    The slug is the identity: ingesting the same document again replaces its
    passages instead of piling a second copy of the same text up.
    """
    slug = slugify(title)
    document = db.execute(
        select(KnowledgeDocumentModel).where(KnowledgeDocumentModel.slug == slug)
    ).scalar_one_or_none()
    if document is None:
        document = KnowledgeDocumentModel(slug=slug)
        db.add(document)
    document.title = title
    document.source = source
    document.source_url = source_url
    document.language = language
    document.published_at = published_at
    db.execute(
        delete(KnowledgeChunkModel).where(KnowledgeChunkModel.document_id == document.id)
    )
    db.flush()

    passages = chunk_text(content)[:MAX_CHUNKS_PER_DOCUMENT]
    chunks = [
        KnowledgeChunkModel(document_id=document.id, ordinal=index, content=passage)
        for index, passage in enumerate(passages)
    ]
    db.add_all(chunks)
    db.flush()
    _embed_chunks(db, chunks)
    db.commit()
    db.refresh(document)
    return document, len(chunks)


def list_documents(db: Session) -> list[tuple[KnowledgeDocumentModel, int]]:
    """Every document of the base, with the number of passages it holds."""
    documents = db.execute(
        select(KnowledgeDocumentModel).order_by(KnowledgeDocumentModel.title)
    ).scalars().all()
    counts = dict(
        db.execute(
            select(KnowledgeChunkModel.document_id, func.count())
            .group_by(KnowledgeChunkModel.document_id)
        ).all()
    )
    return [(document, counts.get(document.id, 0)) for document in documents]


def _vector_search(db: Session, query: str, top_k: int) -> list[dict]:
    vector = embeddings.embed(query)
    rows = db.execute(
        text(
            "SELECT c.id, c.document_id, c.content, d.title, d.source, d.source_url "
            "FROM knowledge_chunks c "
            "JOIN knowledge_documents d ON d.id = c.document_id "
            "WHERE c.embedding IS NOT NULL "
            "AND c.embedding <=> CAST(:vector AS vector) < :distance "
            "ORDER BY c.embedding <=> CAST(:vector AS vector) ASC "
            "LIMIT :top_k"
        ),
        {
            "vector": embeddings.vector_literal(vector),
            "distance": settings.KNOWLEDGE_MAX_DISTANCE,
            "top_k": top_k,
        },
    ).mappings().all()
    return [dict(row) for row in rows]


def _search_terms(query: str) -> str:
    """The words of the query, joined by "or".

    Her question is a sentence, and a sentence does not exist in the document:
    "pilule du lendemain combien de temps" matches nothing with an "and". The
    words are joined by "or" and the rank orders what comes back.
    """
    words = [
        word
        for word in re.findall(r"[\w\u00c0-\u00ff]{4,}", (query or "").lower())
        if word not in _STOP_WORDS
    ]
    if not words:
        return ""
    return " | ".join(dict.fromkeys(words[:12]))


def _fulltext_search(db: Session, query: str, top_k: int) -> list[dict]:
    terms = _search_terms(query)
    if not terms:
        return []
    rows = db.execute(
        text(
            "SELECT c.id, c.document_id, c.content, d.title, d.source, d.source_url "
            "FROM knowledge_chunks c "
            "JOIN knowledge_documents d ON d.id = c.document_id "
            "WHERE to_tsvector('french', c.content) @@ to_tsquery('french', :terms) "
            "ORDER BY ts_rank(to_tsvector('french', c.content), to_tsquery('french', :terms)) DESC "
            "LIMIT :top_k"
        ),
        {"terms": terms, "top_k": top_k},
    ).mappings().all()
    return [dict(row) for row in rows]


def search_chunks(db: Session, query: str, top_k: int | None = None) -> list[dict]:
    """The passages about her question, the closest first.

    Semantic first with a full-text fallback, like the recall over her
    exchanges. An empty list means the base has nothing about it: the bot
    then says it does not know, instead of filling the gap from its memory.

    The search is PostgreSQL only: the full-text side needs the tsvector
    functions and the semantic side the vector type. On any other database the
    base has nothing to say, which is better than an error on the way to the
    model.
    """
    if db.bind is None or db.bind.dialect.name != "postgresql":
        return []
    limit = top_k or settings.KNOWLEDGE_TOP_K
    if embeddings.is_configured():
        try:
            found = _vector_search(db, query, limit)
            if found:
                return found
        except embeddings.EmbeddingsUnavailable as exc:
            LOGGER.warning("Knowledge search fell back to full-text: %s", type(exc).__name__)
    return _fulltext_search(db, query, limit)
