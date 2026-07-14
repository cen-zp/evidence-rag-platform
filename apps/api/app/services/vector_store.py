from collections.abc import Sequence
from uuid import UUID

from qdrant_client import QdrantClient, models

from app.models import DocumentChunk


class QdrantVectorStore:
    def __init__(self, client: QdrantClient, collection_name: str, vector_size: int) -> None:
        self._client = client
        self._collection_name = collection_name
        self._vector_size = vector_size

    def replace_document_chunks(
        self,
        chunks: Sequence[DocumentChunk],
        vectors: Sequence[list[float]],
    ) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("Every chunk must have exactly one vector")
        if not chunks:
            return

        self._ensure_collection()
        document_id = str(chunks[0].document_id)
        self.delete_document_chunks(UUID(document_id))
        self._client.upsert(
            collection_name=self._collection_name,
            points=[
                models.PointStruct(
                    id=chunk.vector_point_id,
                    vector=vector,
                    payload={
                        "knowledge_base_id": str(chunk.knowledge_base_id),
                        "document_id": str(chunk.document_id),
                        "chunk_index": chunk.chunk_index,
                        "page_number": chunk.page_number,
                        "content": chunk.content,
                    },
                )
                for chunk, vector in zip(chunks, vectors, strict=True)
            ],
            wait=True,
        )

    def delete_document_chunks(self, document_id: UUID) -> None:
        self._client.delete(
            collection_name=self._collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value=str(document_id)),
                        )
                    ]
                )
            ),
            wait=True,
        )

    def _ensure_collection(self) -> None:
        if not self._client.collection_exists(self._collection_name):
            self._client.create_collection(
                collection_name=self._collection_name,
                vectors_config=models.VectorParams(
                    size=self._vector_size,
                    distance=models.Distance.COSINE,
                ),
            )
