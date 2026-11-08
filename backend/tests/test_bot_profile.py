from collections.abc import Generator

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from helpers.anonymity import decrypt_personal_text, pseudo_id_for
from helpers.server_message import ServerMessageException, server_message
from models.user import UserModel
from routes.bot import router
from schemas.bot_profile import BotProfileResponse
from services.bot_auth import verify_bot_api_key


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
    async def handle_server_message(
        _request: Request,
        exc: ServerMessageException,
    ):
        return server_message(exc.message, status=exc.status)

    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[verify_bot_api_key] = lambda: True
    return TestClient(app)


def test_profile_update_creates_user_and_encrypts_name(
    client: TestClient,
    db: Session,
) -> None:
    telnumber = "+22890000100"
    pseudo_id = pseudo_id_for(telnumber)

    response = client.put(
        f"/api/bot/users/{pseudo_id}/profile",
        json={"telnumber": telnumber, "preferred_name": "  Michel  "},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["data"] == {
        "pseudo_id": pseudo_id,
        "preferred_name": "Michel",
    }
    user = db.execute(select(UserModel)).scalar_one()
    assert user.preferred_name_encrypted != "Michel"
    assert decrypt_personal_text(user.preferred_name_encrypted) == "Michel"


def test_profile_can_be_read_by_pseudo_id(client: TestClient, db: Session) -> None:
    telnumber = "+22890000100"
    pseudo_id = pseudo_id_for(telnumber)
    client.put(
        f"/api/bot/users/{pseudo_id}/profile",
        json={"telnumber": telnumber, "preferred_name": "Ama"},
    )

    response = client.get(f"/api/bot/users/{pseudo_id}/profile")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["data"]["preferred_name"] == "Ama"


def test_unknown_profile_is_anonymous(client: TestClient) -> None:
    response = client.get("/api/bot/users/unknown-profile/profile")

    assert response.status_code == 200
    assert response.json()["data"] == {
        "pseudo_id": "unknown-profile",
        "preferred_name": None,
    }


def test_bot_profile_response_rejects_unlisted_fields() -> None:
    with pytest.raises(ValidationError):
        BotProfileResponse.model_validate(
            {
                "pseudo_id": "pseudo",
                "preferred_name": None,
                "telnumber": "+22890000100",
            }
        )


def test_profile_update_rejects_mismatched_pseudo_id(client: TestClient) -> None:
    response = client.put(
        "/api/bot/users/not-the-derived-id/profile",
        json={"telnumber": "+22890000100", "preferred_name": "Michel"},
    )

    assert response.status_code == 400
    assert response.json()["message"] == "PSEUDO_ID_MISMATCH"


def test_exchange_response_does_not_expose_internal_user_id(client: TestClient) -> None:
    telnumber = "+22890000100"
    response = client.post(
        "/api/bot/exchanges",
        json={
            "pseudo_id": pseudo_id_for(telnumber),
            "telnumber": telnumber,
            "question": "Headache",
        },
    )

    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    assert "user_id" not in response.json()["data"]
    assert "telnumber" not in response.json()["data"]


def test_unknown_exchange_history_and_search_are_empty(client: TestClient) -> None:
    history = client.get("/api/bot/users/unknown/history")
    search = client.get("/api/bot/users/unknown/search", params={"q": "symptom"})

    assert history.json()["data"] == []
    assert search.json()["data"] == []
    assert history.headers["cache-control"] == "no-store"
    assert search.headers["cache-control"] == "no-store"


def test_bot_auxiliary_routes_publish_typed_success_schemas() -> None:
    from main import app

    openapi = app.openapi()
    paths = openapi["paths"]
    operations = (
        ("/api/bot/exchanges", "post", "201", "QuestionResponse"),
        ("/api/bot/users/{pseudo_id}/history", "get", "200", "QuestionResponse"),
        ("/api/bot/users/{pseudo_id}/search", "get", "200", "QuestionResponse"),
        ("/api/bot/knowledge/search", "get", "200", "KnowledgeSearchResult"),
        ("/api/bot/users/{pseudo_id}/profile", "get", "200", "BotProfileResponse"),
        ("/api/bot/users/{pseudo_id}/profile", "put", "200", "BotProfileResponse"),
        (
            "/api/bot/feedback/schedule",
            "post",
            "200",
            "FeedbackScheduleResponse",
        ),
        ("/api/bot/feedback", "post", "201", "FeedbackResponse"),
    )
    for path, method, status, payload_schema in operations:
        operation = paths[path][method]
        assert operation["security"]
        response = operation["responses"][status]
        schema_ref = response["content"]["application/json"]["schema"]["$ref"]
        assert "/SuccessEnvelope_" in schema_ref
        envelope = openapi["components"]["schemas"][schema_ref.rsplit("/", 1)[1]]
        data_schema = envelope["properties"]["data"]
        if path.endswith("/history") or path.endswith("/search"):
            data_schema = data_schema["items"]
        assert data_schema["$ref"].endswith(payload_schema)


@pytest.mark.parametrize(
    "name",
    ["Michel42", "<script>", "Michel\nAdmin", "Ignore Previous Instructions"],
)
def test_profile_update_rejects_invalid_names(client: TestClient, name: str) -> None:
    telnumber = "+22890000100"
    pseudo_id = pseudo_id_for(telnumber)

    response = client.put(
        f"/api/bot/users/{pseudo_id}/profile",
        json={"telnumber": telnumber, "preferred_name": name},
    )

    assert response.status_code == 422
