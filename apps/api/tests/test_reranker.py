from uuid import uuid4

from app.services.reranker import LocalBgeReranker


class FakeCrossEncoder:
    def __init__(self) -> None:
        self.calls: list[tuple[list[tuple[str, str]], bool]] = []

    def predict(self, pairs, *, show_progress_bar: bool):
        self.calls.append((pairs, show_progress_bar))
        return [0.2, 0.9]


def test_local_bge_reranker_orders_candidates_by_cross_encoder_score() -> None:
    first_id = uuid4()
    second_id = uuid4()
    model = FakeCrossEncoder()
    reranker = LocalBgeReranker("test-model", "cpu", model=model)

    results = reranker.rerank(
        "How does retrieval work?",
        [(first_id, "first document"), (second_id, "second document")],
    )

    assert model.calls == [
        (
            [
                ("How does retrieval work?", "first document"),
                ("How does retrieval work?", "second document"),
            ],
            False,
        )
    ]
    assert [(result.chunk_id, result.score) for result in results] == [
        (second_id, 0.9),
        (first_id, 0.2),
    ]
