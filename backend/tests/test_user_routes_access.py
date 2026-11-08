"""Les routes qui listent, lisent ou créent des comptes sont réservées aux
admins : sans jeton elles exposaient la liste des utilisatrices et les
emails des admins, et permettaient de créer un compte."""

from collections.abc import Generator
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from helpers.server_message import ServerMessageException, server_message
from models.user import UserModel
from routes.admins import router as admins_router
from routes.users import router as users_router
from services.auth_service import get_current_active_user

USER_ID = "00000000-0000-0000-0000-000000000001"
PROTECTED = [
    ("get", "/api/users"),
    ("get", f"/api/users/{USER_ID}"),
    ("post", "/api/users"),
    ("get", "/api/admins"),
    ("get", f"/api/admins/{USER_ID}"),
]


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


def _app(db: Session) -> FastAPI:
    app = FastAPI()

    @app.exception_handler(ServerMessageException)
    async def handle(_request: Request, exc: ServerMessageException):
        return server_message(exc.message, data=exc.data, meta=exc.meta, status=exc.status)

    app.include_router(users_router)
    app.include_router(admins_router)
    app.dependency_overrides[get_db] = lambda: db
    return app


def _call(client: TestClient, method: str, path: str):
    if method == "post":
        return client.post(path, json={"email": "x@example.com", "password": "Secret123!"})
    return client.get(path)


@pytest.mark.parametrize("method,path", PROTECTED)
def test_refused_without_token(db: Session, method: str, path: str) -> None:
    response = _call(TestClient(_app(db)), method, path)
    assert response.status_code in (401, 403)


@pytest.mark.parametrize("method,path", PROTECTED)
def test_refused_for_a_regular_account(db: Session, method: str, path: str) -> None:
    app = _app(db)
    app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(
        is_admin=False, is_active=True, id=None
    )
    response = _call(TestClient(app), method, path)
    assert response.status_code == 403


def test_admin_can_list_users_and_admins(db: Session) -> None:
    app = _app(db)
    app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(
        is_admin=True, is_active=True, id=None
    )
    client = TestClient(app)
    users = client.get("/api/users")
    admins = client.get("/api/admins")
    assert users.status_code == 200
    assert admins.status_code == 200
    for response, message in ((users, "USERS_FETCHED"), (admins, "ADMINS_FETCHED")):
        payload = response.json()
        assert payload["message"] == message
        assert payload["data"] == []
        assert payload["meta"]["current_page"] == 1
        assert payload["meta"]["total_count"] == 0
        assert payload["meta"]["has_more"] is False
        assert payload["meta"]["request_id"]
        assert payload["meta"]["served_at"]


def test_user_and_admin_list_routes_document_typed_success_contracts(
    db: Session,
) -> None:
    schema = _app(db).openapi()
    for path in ("/api/users", "/api/admins"):
        response_schema = schema["paths"][path]["get"]["responses"]["200"]
        success_ref = response_schema["content"]["application/json"]["schema"]["$ref"]
        assert success_ref.endswith(
            "/SuccessEnvelope_list_UserResponse__UserPaginationMetadata_"
        )

    pagination_schema = schema["components"]["schemas"]["UserPaginationMetadata"]
    assert {
        "request_id",
        "served_at",
        "current_page",
        "total_pages",
        "total_count",
        "page_size",
        "has_more",
    } <= set(pagination_schema["properties"])


def _add_user(db: Session, email: str, is_admin: bool = False) -> UserModel:
    user = UserModel(
        pseudo_id=f"pseudo-{uuid4().hex}",
        email=email,
        password_hash="test-hash",
        fullname="Before",
        is_admin=is_admin,
        is_active=True,
    )
    db.add(user)
    db.commit()
    return user


def test_user_responses_allowlist_fields_and_preserve_anonymization(
    db: Session,
) -> None:
    _add_user(db, "user@example.org")
    _add_user(db, "admin@example.org", is_admin=True)
    app = _app(db)
    app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(
        is_admin=True, is_active=True, id=None
    )
    client = TestClient(app)

    regular_user = client.get("/api/users").json()["data"][0]
    admin_user = client.get("/api/admins").json()["data"][0]

    assert regular_user["fullname"] is None
    assert regular_user["email"] is None
    assert regular_user["telnumber_masked"] is None
    assert "telnumber" not in regular_user
    assert admin_user["email"] == "admin@example.org"
    assert admin_user["is_admin"] is True
    assert "telnumber" not in admin_user


def test_user_update_scopes_the_target_in_the_database_query(db: Session) -> None:
    owner = _add_user(db, "owner@example.org")
    other = _add_user(db, "other@example.org")
    app = _app(db)
    app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(
        id=owner.id, is_admin=False, is_active=True
    )

    response = TestClient(app).put(
        f"/api/users/{other.id}", json={"fullname": "Changed"}
    )

    assert response.status_code == 404
    assert response.json()["message"] == "USER_NOT_FOUND"
    db.refresh(other)
    assert other.fullname == "Before"


def test_user_can_update_own_record_with_typed_response(db: Session) -> None:
    user = _add_user(db, "owner@example.org")
    app = _app(db)
    app.dependency_overrides[get_current_active_user] = lambda: SimpleNamespace(
        id=user.id, is_admin=False, is_active=True
    )

    response = TestClient(app).put(
        f"/api/users/{user.id}", json={"fullname": "After"}
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "id": str(user.id),
        "updated_fields": ["fullname"],
    }
    db.refresh(user)
    assert user.fullname == "After"
