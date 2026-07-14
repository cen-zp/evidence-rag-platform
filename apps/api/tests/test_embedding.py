import pytest

from app.services.embedding import LocalBgeEmbedding


class FakeSentenceTransformer:
    def get_embedding_dimension(self) -> int:
        return 3

    def encode(self, texts, *, normalize_embeddings: bool, show_progress_bar: bool):
        assert normalize_embeddings is True
        assert show_progress_bar is False
        return [[float(index), 0.0, 1.0] for index, _ in enumerate(texts)]


def test_local_bge_embedding_normalizes_and_batches_vectors() -> None:
    embedding = LocalBgeEmbedding(
        model_name="test-model",
        dimension=3,
        device="cpu",
        model=FakeSentenceTransformer(),
    )

    assert embedding.embed_query("question") == [0.0, 0.0, 1.0]
    assert embedding.embed_documents(["first", "second"]) == [
        [0.0, 0.0, 1.0],
        [1.0, 0.0, 1.0],
    ]


def test_local_bge_embedding_rejects_dimension_mismatch() -> None:
    with pytest.raises(ValueError, match="does not match"):
        LocalBgeEmbedding(
            model_name="test-model",
            dimension=4,
            device="cpu",
            model=FakeSentenceTransformer(),
        )
