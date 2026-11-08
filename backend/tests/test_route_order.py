"""The routes of the corpus, and the order they are in.

A route that takes a parameter declared before a fixed one swallows it:
"/corpus/scan" would be matched by "/corpus/{slug}" and read as a document.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from routes.knowledge import router as knowledge_router
from services.auth_service import get_current_active_user
from unittest.mock import MagicMock


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture()
def client(db):
    app = FastAPI()
    app.include_router(knowledge_router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_active_user] = lambda: MagicMock(is_admin=True)
    return TestClient(app)


class TestRouteOrder:
    def test_the_scan_is_not_read_as_a_document(self, client: TestClient) -> None:
        response = client.post("/api/knowledge/corpus/scan")

        assert response.status_code == 200, response.text
        assert response.json()["message"] == "KNOWLEDGE_CORPUS_SCANNED"
