import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import get_db
from helpers.server_message import ServerMessageException, server_message
from schemas.knowledge import KnowledgeDocumentCreate, KnowledgeDocumentResponse
from services.auth_service import get_current_active_user
from models.knowledge import KnowledgeChunkModel, KnowledgeDocumentModel
from services.knowledge import ingest_document, list_documents
from services.knowledge_corpus import (
    apply,
    get_document,
    list_documents as list_corpus_documents,
    scan,
)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


class CorpusApply(BaseModel):
    """The content somebody read, to write in the corpus."""

    content: str = Field(min_length=1, max_length=400_000)



def _require_admin(current_user) -> None:
    if not current_user.is_admin:
        raise ServerMessageException("UNAUTHORIZED_ACCESS", status=403)


def _serialize(document, chunk_count: int) -> dict:
    payload = KnowledgeDocumentResponse.model_validate(document).model_dump()
    payload["chunk_count"] = chunk_count
    return payload

@router.get("/documents")
def list_known_documents(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    _require_admin(current_user)
    documents = [_serialize(document, count) for document, count in list_documents(db)]
    return server_message("KNOWLEDGE_DOCUMENTS_FETCHED", data=documents)


@router.post("/documents")
def ingest_known_document(
    data: KnowledgeDocumentCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Puts a document in the base: WHO, UNFPA, a national protocol.

    The same document ingested again replaces its passages instead of piling
    a second copy of the same text up.
    """
    _require_admin(current_user)
    document, chunk_count = ingest_document(
        db,
        title=data.title,
        content=data.content,
        source=data.source,
        source_url=data.source_url,
        language=data.language,
        published_at=data.published_at,
    )
    return server_message(
        "KNOWLEDGE_DOCUMENT_INGESTED",
        data=_serialize(document, chunk_count),
        status=201,
    )


@router.get("/documents/{document_id}")
def get_known_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    _require_admin(current_user)
    for document, count in list_documents(db):
        if document.id == document_id:
            return server_message(
                "KNOWLEDGE_DOCUMENTS_FETCHED", data=[_serialize(document, count)]
            )
    raise ServerMessageException("KNOWLEDGE_DOCUMENT_NOT_FOUND", status=404)


@router.get("/corpus")
def fetch_corpus(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Every document of the corpus, with the passages it holds in the base."""
    _require_admin(current_user)
    counts = _passage_counts(db)
    documents = [
        document.as_dict(counts.get(document.slug, 0))
        for document in list_corpus_documents()
    ]
    return server_message("KNOWLEDGE_CORPUS_FETCHED", data=documents)


@router.post("/corpus/scan")
def scan_corpus(
    current_user=Depends(get_current_active_user),
):
    """Fetches every source and says what changed. Nothing is written."""
    _require_admin(current_user)
    return server_message("KNOWLEDGE_CORPUS_SCANNED", data=scan())


@router.get("/corpus/{slug}")
def fetch_corpus_document(
    slug: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """One document of the corpus, to read it."""
    _require_admin(current_user)
    document = get_document(slug)
    if document is None:
        raise ServerMessageException("KNOWLEDGE_DOCUMENT_NOT_FOUND", status=404)
    counts = _passage_counts(db)
    return server_message(
        "KNOWLEDGE_CORPUS_FETCHED",
        data={**document.as_dict(counts.get(document.slug, 0)), "content": document.content},
    )


@router.post("/corpus/{slug}/apply")
def apply_corpus_document(
    slug: str,
    data: CorpusApply,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_active_user),
):
    """Writes a document somebody has read, and puts its passages in the base.

    The content comes from the body: the file is written from what the reviewer
    saw, never from a second download.
    """
    _require_admin(current_user)
    document = get_document(slug)
    if document is None:
        raise ServerMessageException("KNOWLEDGE_DOCUMENT_NOT_FOUND", status=404)
    content = (data.content or "").strip()
    if not content:
        raise ServerMessageException("CORPUS_CONTENT_REQUIRED", status=400)
    apply(document, content)
    _, count = ingest_document(
        db,
        title=document.title,
        content=content,
        source=document.source,
        source_url=document.source_url,
        language=document.language,
    )
    return server_message(
        "KNOWLEDGE_CORPUS_APPLIED",
        data={**document.as_dict(count), "content": content},
    )


def _passage_counts(db: Session) -> dict:
    """How many passages of the base each document holds."""
    rows = db.execute(
        select(KnowledgeChunkModel.document_id, func.count())
        .group_by(KnowledgeChunkModel.document_id)
    ).all()
    documents = {
        document.id: document
        for document in db.execute(select(KnowledgeDocumentModel)).scalars().all()
    }
    counts = {}
    for document_id, count in rows:
        document = documents.get(document_id)
        if document is not None:
            counts[document.slug] = int(count)
    return counts
