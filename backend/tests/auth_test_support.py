from collections.abc import Generator

import pytest
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from config import settings
from database import Base, get_db
from helpers.server_message import ServerMessageException, server_message
from models.user import UserModel
from routes.auth import router
from routes.auth_mfa import router as auth_mfa_router
from services.auth_service import hash_password


@pytest.fixture()
def login_db() -> Generator[Session, None, None]:
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
def login_client(
    login_db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    monkeypatch.setattr(settings, "ADMIN_LOGIN_BUCKET_KEY", SecretStr("11" * 32))
    monkeypatch.setattr(settings, "LOGIN_TRUSTED_PROXY_HOPS", 0)
    app = FastAPI()

    @app.exception_handler(ServerMessageException)
    async def server_error(_request: Request, exc: ServerMessageException):
        return server_message(
            exc.message,
            data=exc.data,
            meta=exc.meta,
            status=exc.status,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, exc: RequestValidationError):
        from main import validation_exception_handler

        return await validation_exception_handler(_request, exc)

    app.include_router(router)
    app.include_router(auth_mfa_router)
    app.dependency_overrides[get_db] = lambda: login_db
    return TestClient(app, client=("127.0.0.1", 123))


def add_auth_user(
    db: Session,
    email: str,
    pseudo_id: str = "a" * 32,
    active: bool = True,
) -> UserModel:
    user = UserModel(
        fullname="Admin",
        pseudo_id=pseudo_id,
        email=email,
        password_hash=hash_password("correct-password"),
        is_admin=True,
        is_active=active,
    )
    db.add(user)
    db.commit()
    return user
