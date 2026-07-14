from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.models import User
from app.services.auth import get_current_user
from app.services.deepseek import DeepSeekProviderError


class RateLimitedService:
    async def chat(self, message: str, history):
        raise DeepSeekProviderError(429, "AI provider rate limit reached. Please retry shortly.")


def test_chat_converts_provider_rate_limit_to_safe_http_error() -> None:
    app = create_app(Settings(app_env="test", deepseek_api_key=None, _env_file=None))
    app.dependency_overrides[get_current_user] = lambda: User(
        email="test@example.com",
        password_hash="test-hash",
    )
    app.state.chat_service_factory = lambda: RateLimitedService()

    response = TestClient(app).post("/api/chat", json={"message": "hello"})

    assert response.status_code == 429
    assert response.json() == {
        "detail": "AI provider rate limit reached. Please retry shortly."
    }
