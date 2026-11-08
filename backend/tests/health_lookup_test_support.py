from collections.abc import Generator

import pytest
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from config import settings
from database import Base, get_db
from helpers.server_message import ServerMessageException, server_message
from routes.health import router

BOT_KEY = "health-test-bot-key"


@pytest.fixture()
def db() -> Generator[Session, None, None]:
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
def client(db: Session, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings, "BOT_API_KEY", BOT_KEY)
    monkeypatch.setattr(settings, "HEALTH_LOOKUP_AUTH_REQUIRED", True)
    monkeypatch.setattr(settings, "HEALTH_NEAREST_RATE_LIMIT_PER_MINUTE", 120)
    monkeypatch.setattr(settings, "HEALTH_GEOCODE_RATE_LIMIT_PER_MINUTE", 30)
    app = FastAPI()

    @app.exception_handler(ServerMessageException)
    async def handle_domain_error(_request: Request, exc: ServerMessageException):
        return server_message(
            exc.message,
            meta=exc.meta,
            status=exc.status,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_request: Request, _exc: RequestValidationError):
        return server_message("VALIDATION_ERROR", status=422)

    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)
