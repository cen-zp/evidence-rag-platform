from app.evaluation.retrieval import RetrievalEvaluationCase, evaluate_retrieval


def test_retrieval_evaluation_reports_recall_mrr_and_latency() -> None:
    cases = [
        RetrievalEvaluationCase(
            id="release",
            question="Where is the release process?",
            expected_filenames=["handbook.md"],
        ),
        RetrievalEvaluationCase(
            id="security",
            question="Where is the security policy?",
            expected_filenames=["security.md"],
        ),
    ]

    def retrieve_filenames(question: str, top_k: int) -> list[str]:
        assert top_k == 2
        if "release" in question:
            return ["overview.md", "handbook.md"]
        return ["overview.md", "security.md"]

    report = evaluate_retrieval(cases, retrieve_filenames, top_k=2)

    assert report.case_count == 2
    assert report.recall_at_k == 1.0
    assert report.mean_reciprocal_rank == 0.5
    assert report.mean_latency_ms >= 0
    assert report.p95_latency_ms >= 0
