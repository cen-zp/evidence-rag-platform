from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    app_name: str = "Evidence RAG API"
    app_env: str = "development"
    web_origin: str = "http://localhost:3000"
    database_url: str = (
        "postgresql+psycopg://evidence_rag:change-me-locally@localhost:5432/evidence_rag"
    )
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "document_chunks_bge_small_zh_v1_5"
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_dimension: int = 512
    embedding_device: str = "cpu"
    reranker_model: str = "BAAI/bge-reranker-base"
    reranker_enabled: bool = True
    reranker_candidate_count: int = 10
    reranker_device: str = "cpu"
    deepseek_api_key: SecretStr | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_chat_model: str = "deepseek-v4-flash"
    deepseek_timeout_seconds: float = 30.0
    deepseek_input_cost_per_million_tokens: float | None = Field(default=None, ge=0)
    deepseek_output_cost_per_million_tokens: float | None = Field(default=None, ge=0)
    deepseek_cost_currency: str = Field(default="CNY", min_length=1, max_length=12)
    auth_session_days: int = 30

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
