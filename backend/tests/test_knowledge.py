import unittest
"""The documentary base: passages, ingestion, and the search the bot asks for.

The model used to invent figures - dosages, prices, durations - because it
answered from its memory. The base gives it passages it may quote, and
nothing else; an empty result is a real answer.
"""
from collections.abc import Generator
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from helpers.server_message import ServerMessageException, server_message
from models.knowledge import KnowledgeChunkModel, KnowledgeDocumentModel
from routes.bot import router as bot_router
from routes.knowledge import router as knowledge_router
from services import knowledge
from services.auth_service import get_current_active_user
from services.bot_auth import verify_bot_api_key

def _paragraph(marker: str, length: int = 600) -> str:
    """A paragraph long enough to stand as its own passage."""
    body = f"{marker} : " + ("texte de démonstration sur la contraception. " * 30)
    return body[:length]


DOCUMENT = {
    "title": "Guide de planification familiale",
    "content": "\n\n".join(
        _paragraph(marker) for marker in ("La contraception combinée", "La pilule d'urgence", "Le test de grossesse")
    ),
    "source": "OMS",
    "source_url": "https://www.who.int/health-topics/contraception",
    "language": "fr",
}


@pytest.fixture()
def db() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture()
def client(db: Session) -> TestClient:
    app = FastAPI()

    @app.exception_handler(ServerMessageException)
    async def handle_server_message(_request: Request, exc: ServerMessageException):
        return server_message(exc.message, data=exc.data, meta=exc.meta, status=exc.status)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_request: Request, exc: RequestValidationError):
        return server_message("VALIDATION_ERROR", status=422)

    app.include_router(bot_router)
    app.include_router(knowledge_router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[verify_bot_api_key] = lambda: True
    app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(is_admin=True)
    return TestClient(app)


class TestChunking:
    def test_paragraphs_are_the_passages(self) -> None:
        chunks = knowledge.chunk_text(DOCUMENT["content"])
        assert len(chunks) == 3
        assert chunks[0].startswith("La contraception combinée")

    def test_short_paragraphs_are_joined(self) -> None:
        """A document made of short paragraphs is still a document."""
        chunks = knowledge.chunk_text("Un.\n\nDeux.\n\nTrois.")
        assert len(chunks) == 1
        assert "Trois." in chunks[0]
    def test_a_long_paragraph_is_cut_on_sentences(self) -> None:
        text = " ".join(
            f"Phrase numéro {index} qui parle de contraception." for index in range(60)
        )
        chunks = knowledge.chunk_text(text, max_chars=300)
        assert len(chunks) > 1
        assert all(len(chunk) <= 300 for chunk in chunks)

    def test_a_short_document_is_kept(self) -> None:
        assert knowledge.chunk_text("Une seule phrase.") == ["Une seule phrase."]

    def test_an_empty_document_yields_nothing(self) -> None:
        assert knowledge.chunk_text("   ") == []

    def test_the_slug_is_stable_and_readable(self) -> None:
        assert knowledge.slugify("Guide de planification familiale") == (
            "guide-de-planification-familiale"
        )
        assert knowledge.slugify("Règles OMS/UNFPA 2026") == "regles-oms-unfpa-2026"


class TestIngestion:
    def test_a_document_is_stored_with_its_passages(self, db: Session) -> None:
        document, count = knowledge.ingest_document(db, **DOCUMENT)

        assert count == 3
        assert document.slug == "guide-de-planification-familiale"
        chunks = db.execute(
            select(KnowledgeChunkModel).where(
                KnowledgeChunkModel.document_id == document.id
            )
        ).scalars().all()
        assert len(chunks) == 3
        assert [chunk.ordinal for chunk in chunks] == [0, 1, 2]

    def test_ingesting_the_same_document_again_replaces_it(self, db: Session) -> None:
        first, _ = knowledge.ingest_document(db, **DOCUMENT)
        second, count = knowledge.ingest_document(
            db,
            title=DOCUMENT["title"],
            content="Un contenu tout autre, assez long pour compter comme un passage.",
            source=DOCUMENT["source"],
        )

        assert second.id == first.id
        assert count == 1
        chunks = db.execute(
            select(KnowledgeChunkModel).where(
                KnowledgeChunkModel.document_id == first.id
            )
        ).scalars().all()
        assert len(chunks) == 1
        assert "tout autre" in chunks[0].content


class TestSearchTerms(unittest.TestCase):
    """Her question is a sentence, and a sentence does not exist in a
    document."""

    def test_the_words_are_joined_by_or(self) -> None:
        terms = knowledge._search_terms("pilule du lendemain combien de temps")

        self.assertIn("pilule |", terms)
        self.assertIn("lendemain", terms)

    def test_the_useless_words_are_left_out(self) -> None:
        terms = knowledge._search_terms("combien de temps pour la pilule")

        self.assertNotIn("combien", terms)
        self.assertIn("pilule", terms)

    def test_a_query_without_a_word_yields_nothing(self) -> None:
        self.assertEqual(knowledge._search_terms("a de"), "")
        self.assertEqual(knowledge._search_terms(""), "")


class TestSearch:
    def _fake_db(self, distance_hits: list[dict], text_hits: list[dict]):
        """A session whose execute records the statements it is given."""
        seen: list[str] = []

        def execute(statement, _params=None):
            text = str(statement)
            seen.append(text)
            mock = MagicMock()
            if "embedding <=" in text:
                mock.mappings.return_value.all.return_value = distance_hits
            else:
                mock.mappings.return_value.all.return_value = text_hits
            return mock

        db = MagicMock()
        db.execute.side_effect = execute
        db.bind.dialect.name = "postgresql"
        return db, seen

    def test_the_semantic_branch_is_used_when_the_embeddings_are_on(self, monkeypatch) -> None:
        monkeypatch.setattr(knowledge.settings, "EMBEDDING_ENABLED", True)
        monkeypatch.setattr(knowledge.embeddings, "is_configured", lambda: True)
        monkeypatch.setattr(
            knowledge.embeddings, "embed", lambda _text: [0.1] * knowledge.settings.EMBEDDING_DIMENSIONS
        )
        hit = {
            "document_id": "d1",
            "content": "un extrait",
            "title": "un titre",
            "source": "OMS",
            "source_url": None,
        }
        db, seen = self._fake_db([hit], [])

        found = knowledge.search_chunks(db, "contraception")

        assert found == [hit]
        assert any("embedding <=" in statement for statement in seen)

    def test_the_full_text_branch_is_the_fallback(self, monkeypatch) -> None:
        monkeypatch.setattr(knowledge.embeddings, "is_configured", lambda: False)
        hit = {
            "document_id": "d1",
            "content": "un extrait",
            "title": "un titre",
            "source": "OMS",
            "source_url": None,
        }
        db, seen = self._fake_db([], [hit])

        found = knowledge.search_chunks(db, "contraception")

        assert found == [hit]
        assert any("to_tsvector" in statement for statement in seen)

    def test_no_passage_is_a_real_answer(self, monkeypatch) -> None:
        monkeypatch.setattr(knowledge.embeddings, "is_configured", lambda: False)
        db, _ = self._fake_db([], [])

        assert knowledge.search_chunks(db, "un sujet absent") == []


class TestRoutes:
    def test_an_admin_puts_a_document_in_the_base(self, client: TestClient) -> None:
        response = client.post("/api/knowledge/documents", json=DOCUMENT)

        assert response.status_code == 201
        body = response.json()
        assert body["message"] == "KNOWLEDGE_DOCUMENT_INGESTED"
        assert body["data"]["slug"] == "guide-de-planification-familiale"
        assert body["data"]["chunk_count"] == 3

    def test_a_document_needs_a_title_and_a_content(self, client: TestClient) -> None:
        response = client.post("/api/knowledge/documents", json={"title": "Sans contenu"})

        assert response.status_code == 422
        assert response.json()["message"] == "VALIDATION_ERROR"

    def test_the_documents_are_listed(self, client: TestClient) -> None:
        client.post("/api/knowledge/documents", json=DOCUMENT)

        response = client.get("/api/knowledge/documents")

        assert response.status_code == 200
        documents = response.json()["data"]
        assert len(documents) == 1
        assert documents[0]["chunk_count"] == 3

    def test_the_bot_searches_the_base(self, client: TestClient, monkeypatch) -> None:
        extract = {
            "document_id": "d1",
            "content": "La pilule du lendemain se prend dans les 72 heures.",
            "title": "Guide de planification familiale",
            "source": "OMS",
            "source_url": "https://www.who.int/health-topics/contraception",
        }
        monkeypatch.setattr("routes.bot.search_chunks", lambda *_args, **_kwargs: [extract])

        response = client.get("/api/bot/knowledge/search", params={"q": "contraception"})

        assert response.status_code == 200
        body = response.json()
        assert body["message"] == "KNOWLEDGE_SEARCHED"
        assert body["data"][0]["source"] == "OMS"
        assert "72 heures" in body["data"][0]["content"]

    def test_the_search_needs_a_question(self, client: TestClient) -> None:
        response = client.get("/api/bot/knowledge/search", params={"q": ""})

        assert response.status_code == 422
        assert response.json()["message"] == "VALIDATION_ERROR"
