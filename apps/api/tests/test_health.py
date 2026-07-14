from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def create_test_client() -> TestClient:
    settings = Settings(app_env="test", deepseek_api_key=None, _env_file=None)
    return TestClient(create_app(settings))


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
