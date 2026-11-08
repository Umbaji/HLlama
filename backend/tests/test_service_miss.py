"""The wordings that named a service and were not understood.

The services of the bot can only grow from what she really says. The record
holds the shape of a sentence, never its content, and never anything about her
health.
"""
from collections.abc import Generator
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from helpers.server_message import ServerMessageException, server_message
from models.service_miss import ServiceMissModel
from routes.service_miss import admin_router, bot_router
from services.auth_service import get_current_active_user
from services.bot_auth import verify_bot_api_key
from services.service_miss import list_misses, record_miss


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
    app.include_router(admin_router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[verify_bot_api_key] = lambda: True
    app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(is_admin=True)
    return TestClient(app)


class TestRecording:
    def test_a_wording_is_recorded(self, db: Session) -> None:
        miss = record_miss(db, "reminder", "rappelle le #")

        assert miss.service == "reminder"
        assert miss.wording == "rappelle le #"
        assert miss.hits == 1

    def test_the_same_wording_is_counted(self, db: Session) -> None:
        record_miss(db, "reminder", "rappelle le #")
        miss = record_miss(db, "reminder", "rappelle le #")

        assert miss.hits == 2
        assert len(db.execute(select(ServiceMissModel)).scalars().all()) == 1

    def test_an_empty_wording_is_refused(self, db: Session) -> None:
        with pytest.raises(ValueError):
            record_miss(db, "reminder", "   ")


class TestRoutes:
    def test_the_bot_records_a_wording(self, client: TestClient) -> None:
        response = client.post(
            "/api/bot/service-misses",
            json={"service": "reminder", "wording": "rappelle le #"},
        )

        assert response.status_code == 201
        assert response.json()["message"] == "SERVICE_MISS_RECORDED"

    def test_a_wording_is_needed(self, client: TestClient) -> None:
        response = client.post("/api/bot/service-misses", json={"wording": ""})

        assert response.status_code == 422

    def test_the_admin_reads_the_wordings(self, client: TestClient) -> None:
        client.post("/api/bot/service-misses", json={"service": "reminder", "wording": "a"})
        client.post("/api/bot/service-misses", json={"service": "reminder", "wording": "a"})

        response = client.get("/api/service-misses")

        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert len(data) == 1
        assert data[0]["hits"] == 2

    def test_the_most_frequent_come_first(self, db: Session) -> None:
        record_miss(db, "reminder", "once")
        for _ in range(3):
            record_miss(db, "message", "often")

        rows = list_misses(db)

        assert rows[0][0].wording == "often"
        assert rows[0][1] == 3
