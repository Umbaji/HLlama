import uuid
from collections.abc import Generator
from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from clients import embeddings
from config import settings
from database import Base
from services import question_service
from services.embeddings import sweep_embeddings

DIM = settings.EMBEDDING_DIMENSIONS


@dataclass
class _Stub:
    id: str


@pytest.fixture(autouse=True)
def embedding_settings(monkeypatch):
    monkeypatch.setattr(settings, "EMBEDDING_ENABLED", True)
    monkeypatch.setattr(settings, "AZURE_OPENAI_ENDPOINT", "https://hllama.openai.azure.com")
    monkeypatch.setattr(settings, "AZURE_OPENAI_API_KEY", "test-embedding-key")
    monkeypatch.setattr(settings, "SEMANTIC_SWEEP_BATCH", 50)
    monkeypatch.setattr(settings, "SEMANTIC_MAX_DISTANCE", 0.65)


@pytest.fixture()
def db() -> Generator[Session, None, None]:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def _unit_vector() -> list[float]:
    return [1.0] + [0.0] * (DIM - 1)


class _OkResponse:
    status_code = 200

    def __init__(self, payload: object):
        self._payload = payload

    def json(self) -> object:
        return self._payload


class _ErrorResponse:
    status_code = 503


class _BrokenJsonResponse:
    status_code = 200

    def json(self) -> object:
        raise ValueError("not json")


class TestEmbed:
    def test_returns_the_vector_from_the_provider(self, monkeypatch):
        monkeypatch.setattr(
            "clients.embeddings.requests.post",
            lambda *args, **kwargs: _OkResponse({"data": [{"embedding": _unit_vector()}]}),
        )
        assert embeddings.embed("règles douloureuses") == _unit_vector()

    def test_raises_when_not_configured(self, monkeypatch):
        monkeypatch.setattr(settings, "EMBEDDING_ENABLED", False)
        monkeypatch.setattr(settings, "AZURE_OPENAI_API_KEY", None)
        with pytest.raises(embeddings.EmbeddingsUnavailable):
            embeddings.embed("règles")

    def test_http_error_raises_unavailable(self, monkeypatch):
        monkeypatch.setattr(
            "clients.embeddings.requests.post",
            lambda *args, **kwargs: _ErrorResponse(),
        )
        with pytest.raises(embeddings.EmbeddingsUnavailable) as exc_info:
            embeddings.embed("règles")
        assert "http_503" in str(exc_info.value)

    def test_malformed_json_raises_unavailable(self, monkeypatch):
        monkeypatch.setattr(
            "clients.embeddings.requests.post",
            lambda *args, **kwargs: _BrokenJsonResponse(),
        )
        with pytest.raises(embeddings.EmbeddingsUnavailable) as exc_info:
            embeddings.embed("règles")
        assert "invalid_json" in str(exc_info.value)

    def test_wrong_length_vector_raises_unavailable(self, monkeypatch):
        payload = {"data": [{"embedding": [0.0, 0.0]}]}
        monkeypatch.setattr(
            "clients.embeddings.requests.post",
            lambda *args, **kwargs: _OkResponse(payload),
        )
        with pytest.raises(embeddings.EmbeddingsUnavailable) as exc_info:
            embeddings.embed("règles")
        assert "missing_vector" in str(exc_info.value)

    def test_transport_error_raises_unavailable(self, monkeypatch):
        import requests

        def fake_post(*_args, **_kwargs):
            raise requests.Timeout()

        monkeypatch.setattr("clients.embeddings.requests.post", fake_post)
        with pytest.raises(embeddings.EmbeddingsUnavailable):
            embeddings.embed("règles")


class TestExtractVector:
    def test_accepts_a_valid_unit_vector(self):
        assert embeddings._extract_vector({"data": [{"embedding": _unit_vector()}]}) == _unit_vector()

    def test_rejects_out_of_range_values(self):
        vector = [2.0] + [0.0] * (DIM - 1)
        assert embeddings._extract_vector({"data": [{"embedding": vector}]}) is None

    @pytest.mark.parametrize(
        "payload",
        [
            None,
            {"data": None},
            {"data": []},
            {"data": "x"},
            {"data": [42]},
            {"data": [{"embedding": "nope"}]},
        ],
    )
    def test_rejects_malformed_payloads(self, payload):
        assert embeddings._extract_vector(payload) is None


class TestVectorLiteral:
    def test_formats_pgvector_literal(self):
        assert embeddings.vector_literal([1.0, -0.25, 0.0]) == "[1.0,-0.25,0.0]"


class TestSweep:
    def test_does_nothing_when_embeddings_disabled(self, db, monkeypatch):
        monkeypatch.setattr(settings, "EMBEDDING_ENABLED", False)
        assert sweep_embeddings(db) == {"embedded": 0, "skipped": 0, "failed": 0}


class TestSearchBranch:
    def _fake_db(self, distance_hits: list[str], fulltext_hits: list[_Stub]):
        """A session whose execute records statements and stubs their results."""
        seen: list[str] = []

        def execute(statement, _params=None):
            text = str(statement)
            seen.append(text)
            mock = MagicMock()
            if "embedding <=>" in text:
                mock.mappings.return_value.all.return_value = [{"id": item} for item in distance_hits]
            else:
                mock.scalars.return_value.all.return_value = fulltext_hits
            return mock

        db = MagicMock()
        db.execute.side_effect = execute
        return db, seen

    def test_fulltext_branch_when_embeddings_disabled(self, monkeypatch):
        monkeypatch.setattr(settings, "EMBEDDING_ENABLED", False)
        monkeypatch.setattr("services.question_service.embeddings.embed", lambda _q: _unit_vector())
        db, seen = self._fake_db([], [_Stub(id="a")])
        result = question_service.search_exchanges(db, uuid.uuid4(), "règles", top_k=3)
        assert result == [_Stub(id="a")]
        assert any("to_tsvector" in call for call in seen)
        assert not any("embedding <=" in call for call in seen)

    def test_semantic_branch_wins_when_a_row_is_close(self, monkeypatch):
        monkeypatch.setattr("services.question_service.embeddings.embed", lambda _q: _unit_vector())
        db, seen = self._fake_db(["abc"], [_Stub(id="abc")])
        result = question_service.search_exchanges(db, uuid.uuid4(), "saignements", top_k=3)
        assert result == [_Stub(id="abc")]
        assert any("embedding <=" in call for call in seen)
        assert not any("to_tsvector" in call for call in seen)

    def test_falls_back_to_fulltext_when_nothing_is_close(self, monkeypatch):
        monkeypatch.setattr("services.question_service.embeddings.embed", lambda _q: _unit_vector())
        db, seen = self._fake_db([], [_Stub(id="b")])
        result = question_service.search_exchanges(db, uuid.uuid4(), "truc", top_k=3)
        assert result == [_Stub(id="b")]
        assert any("embedding <=" in call for call in seen)
        assert any("to_tsvector" in call for call in seen)

    def test_embedding_failure_falls_back_to_fulltext(self, monkeypatch):
        def broken_embed(_query: str) -> list[float]:
            raise embeddings.EmbeddingsUnavailable("http_503")

        monkeypatch.setattr("services.question_service.embeddings.embed", broken_embed)
        db, seen = self._fake_db([], [_Stub(id="c")])
        result = question_service.search_exchanges(db, uuid.uuid4(), "règles", top_k=3)
        assert result == [_Stub(id="c")]
        assert any("to_tsvector" in call for call in seen)
        assert not any("embedding <=" in call for call in seen)