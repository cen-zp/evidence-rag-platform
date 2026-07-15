from app.core.config import Settings
from app.evaluation.runner import build_run_metadata


def test_run_metadata_excludes_secrets_and_omits_disabled_reranker_details() -> None:
    settings = Settings(
        _env_file=None,
        embedding_model="test-embedding",
        embedding_dimension=128,
        embedding_device="cpu",
        qdrant_collection="test-collection",
        reranker_model="test-reranker",
        reranker_candidate_count=12,
    )

    without_reranker = build_run_metadata(
        settings, reranker_enabled=False, warmup_queries=0
    )
    with_reranker = build_run_metadata(settings, reranker_enabled=True, warmup_queries=3)

    assert without_reranker["embedding_model"] == "test-embedding"
    assert without_reranker["reranker_model"] is None
    assert without_reranker["reranker_candidate_count"] is None
    assert without_reranker["warmup_queries_excluded"] == 0
    assert with_reranker["reranker_model"] == "test-reranker"
    assert with_reranker["reranker_candidate_count"] == 12
    assert with_reranker["warmup_queries_excluded"] == 3
    assert "deepseek_api_key" not in with_reranker
