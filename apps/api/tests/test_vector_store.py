from uuid import uuid4

from app.services.vector_store import QdrantVectorStore


class MissingCollectionClient:
    def collection_exists(self, collection_name: str) -> bool:
        assert collection_name == "new-collection"
        return False

    def query_points(self, **kwargs):
        raise AssertionError("A missing collection must not be queried")


def test_search_returns_no_hits_before_new_collection_is_indexed() -> None:
    vector_store = QdrantVectorStore(
        client=MissingCollectionClient(),
        collection_name="new-collection",
        vector_size=512,
    )

    assert vector_store.search(uuid4(), [0.0] * 512, limit=5) == []
