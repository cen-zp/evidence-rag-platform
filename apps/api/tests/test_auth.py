import sqlite3
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.db.base import Base
from app.db.session import create_session_factory, get_session
from app.main import create_app


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection: sqlite3.Connection, _connection_record) -> None:
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    app = create_app(Settings(app_env="test", deepseek_api_key=None, _env_file=None))

    def override_session() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def register(client: TestClient, email: str) -> dict:
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": "correct-horse-battery-staple"},
    )
    assert response.status_code == 201
    return response.json()


def auth_headers(session: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {session['access_token']}"}


def test_register_login_logout_and_require_bearer_authentication(client: TestClient) -> None:
    unauthenticated = client.get("/api/knowledge-bases")
    assert unauthenticated.status_code == 401

    registered = register(client, "owner@example.com")
    assert registered["user"]["email"] == "owner@example.com"

    created = client.post(
        "/api/knowledge-bases",
        headers=auth_headers(registered),
        json={"name": "Owner knowledge base"},
    )
    assert created.status_code == 201
    assert created.json()["owner_id"] == registered["user"]["id"]

    logout = client.post("/api/auth/logout", headers=auth_headers(registered))
    assert logout.status_code == 204
    assert client.get("/api/knowledge-bases", headers=auth_headers(registered)).status_code == 401

    login = client.post(
        "/api/auth/login",
        json={"email": "owner@example.com", "password": "correct-horse-battery-staple"},
    )
    assert login.status_code == 200
    assert client.get("/api/auth/me", headers=auth_headers(login.json())).json() == (
        registered["user"]
    )


def test_knowledge_bases_are_not_visible_across_authenticated_users(client: TestClient) -> None:
    owner = register(client, "owner@example.com")
    created = client.post(
        "/api/knowledge-bases",
        headers=auth_headers(owner),
        json={"name": "Owner knowledge base"},
    ).json()
    other_user = register(client, "other@example.com")

    assert client.get("/api/knowledge-bases", headers=auth_headers(other_user)).json() == []
    response = client.get(
        f"/api/knowledge-bases/{created['id']}/documents",
        headers=auth_headers(other_user),
    )
    assert response.status_code == 404
