"""What she declared about her health, kept only with her agreement.

A fact she got wrong must be correctable, and a fact of somebody else must
not exist in these endpoints.
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
from models.health_fact import HealthFactModel
from routes.health_fact import router as health_facts_router
from services.bot_auth import verify_bot_api_key
from services.health_fact import (
    FactNotFound,
    list_facts,
    record_fact,
    remove_fact,
)
from services.user_service import get_or_create_bot_user

PSEUDO = "a1b2c3d4e5f6a7b8c9d0"
OTHER_PSEUDO = "ffffffffffffffffffff"
TEL = "+22890000100"


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

    app.include_router(health_facts_router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[verify_bot_api_key] = lambda: True
    return TestClient(app)


def _user(db: Session, pseudo_id: str = PSEUDO, tel: str = TEL):
    return get_or_create_bot_user(db, pseudo_id, tel)


class TestFacts:
    def test_a_fact_is_kept_with_the_agreement(self, db: Session) -> None:
        user = _user(db)

        fact = record_fact(db, PSEUDO, user.id, "je suis allergique à la pénicilline")

        assert fact.fact == "je suis allergique à la pénicilline"
        assert fact.consented_at is not None
        assert fact.active is True

    def test_the_facts_are_her_own(self, db: Session) -> None:
        user = _user(db)
        record_fact(db, PSEUDO, user.id, "un fait à moi")

        assert len(list_facts(db, PSEUDO)) == 1
        assert list_facts(db, OTHER_PSEUDO) == []

    def test_a_removed_fact_is_not_listed_anymore(self, db: Session) -> None:
        user = _user(db)
        fact = record_fact(db, PSEUDO, user.id, "un fait")

        remove_fact(db, fact.id, PSEUDO)

        assert list_facts(db, PSEUDO) == []
        row = db.execute(
            select(HealthFactModel).where(HealthFactModel.id == fact.id)
        ).scalar_one()
        assert row.active is False
        assert row.removed_at is not None

    def test_a_fact_of_somebody_else_does_not_exist(self, db: Session) -> None:
        user = _user(db)
        fact = record_fact(db, PSEUDO, user.id, "un fait")

        with pytest.raises(FactNotFound):
            remove_fact(db, fact.id, OTHER_PSEUDO)

    def test_an_empty_fact_is_refused(self, db: Session) -> None:
        user = _user(db)
        with pytest.raises(ValueError):
            record_fact(db, PSEUDO, user.id, "   ")


class TestRoutes:
    def test_a_fact_is_recorded(self, client: TestClient, db: Session) -> None:
        _user(db)

        response = client.post(
            "/api/bot/health-facts",
            json={"pseudo_id": PSEUDO, "fact": "je suis allergique à la pénicilline"},
        )

        assert response.status_code == 201
        assert response.json()["message"] == "HEALTH_FACT_RECORDED"

    def test_the_facts_are_read(self, client: TestClient, db: Session) -> None:
        _user(db)
        client.post(
            "/api/bot/health-facts",
            json={"pseudo_id": PSEUDO, "fact": "un fait"},
        )

        response = client.get(f"/api/bot/users/{PSEUDO}/health-facts")

        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    def test_a_fact_is_removed(self, client: TestClient, db: Session) -> None:
        _user(db)
        created = client.post(
            "/api/bot/health-facts",
            json={"pseudo_id": PSEUDO, "fact": "un fait"},
        ).json()["data"]

        response = client.post(
            f"/api/bot/health-facts/{created['id']}/remove", params={"pseudo_id": PSEUDO}
        )

        assert response.status_code == 200
        assert response.json()["message"] == "HEALTH_FACT_REMOVED"

    def test_an_unknown_person_is_refused(self, client: TestClient) -> None:
        response = client.post(
            "/api/bot/health-facts",
            json={"pseudo_id": OTHER_PSEUDO, "fact": "un fait"},
        )

        assert response.status_code == 404
        assert response.json()["message"] == "USER_NOT_FOUND"
