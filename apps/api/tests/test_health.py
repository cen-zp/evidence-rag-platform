from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.models import User
from app.services.auth import get_current_user


def create_test_client() -> TestClient:
    settings = Settings(app_env="test", deepseek_api_key=None, _env_file=None)
    app = create_app(settings)
    app.state.knowledge_base_retriever_factory = _unexpected_retriever_factory
    app.dependency_overrides[get_current_user] = lambda: User(
        email="test@example.com",
        password_hash="test-hash",
    )
    return TestClient(app)


def _unexpected_retriever_factory() -> None:
    raise AssertionError("A direct chat request should not initialize the knowledge-base retriever")


def test_health_check() -> None:
    response = create_test_client().get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "environment": "test"}


def test_chat_returns_503_without_api_key() -> None:
    response = create_test_client().post("/api/chat", json={"message": "hello"})

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "AI provider is not configured. Add DEEPSEEK_API_KEY to the local .env file."
    )


def test_cors_allows_only_the_workbench_origin_and_required_request_shape() -> None:
    response = create_test_client().options(
        "/api/chat",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization, Content-Type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert response.headers["access-control-allow-methods"] == "GET, POST, DELETE, OPTIONS"
    assert response.headers["access-control-allow-headers"] == (
        "Accept, Accept-Language, Authorization, Content-Language, Content-Type"
    )


def test_cors_rejects_unneeded_request_method() -> None:
    response = create_test_client().options(
        "/api/chat",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "PATCH",
        },
    )

    assert response.status_code == 400
