import asyncio
import csv
from types import SimpleNamespace
from uuid import UUID, uuid4

from app.evaluation.answer_batch import (
    build_answer_batch_report,
    run_answer_batch,
    write_answer_review_sheet,
)
from app.evaluation.retrieval import RetrievalEvaluationCase
from app.schemas.chat import ChatUsage
from app.services.deepseek import (
    DeepSeekInvalidCitationError,
    GroundedModelResponse,
)


def make_hit(chunk_id: UUID, filename: str = "source.md"):
    return SimpleNamespace(
        chunk=SimpleNamespace(
            id=chunk_id,
            content="Source content",
            document=SimpleNamespace(filename=filename),
        )
    )


class FakeRetriever:
    def __init__(self, hits_by_question):
        self.hits_by_question = hits_by_question

    def search(self, _knowledge_base_id, query, top_k):
        return self.hits_by_question[query][:top_k]


class FakeService:
    def __init__(self, response):
        self.response = response

    async def chat_with_evidence(self, _message, _evidence, _history):
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def test_answer_batch_captures_grounded_output_and_generates_pending_review_sheet(tmp_path) -> None:
    chunk_id = uuid4()
    cases = [
        RetrievalEvaluationCase(
            id="case-1",
            question="What is documented?",
            expected_filenames=["source.md"],
            reference_answer="The source documents it.",
        )
    ]
    response = GroundedModelResponse(
        answer="The source documents it.",
        citation_ids=[chunk_id],
        model="test-model",
        latency_ms=123,
        usage=ChatUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )

    results = asyncio.run(
        run_answer_batch(
            uuid4(),
            cases,
            FakeRetriever({"What is documented?": [make_hit(chunk_id)]}),
            FakeService(response),
            top_k=3,
        )
    )
    report = build_answer_batch_report(results)
    review_path = tmp_path / "answer-review.csv"
    write_answer_review_sheet(results, review_path)

    assert report["answered_count"] == 1
    assert report["total_tokens"] == 15
    assert results[0].citations[0].filename == "source.md"
    with review_path.open(encoding="utf-8-sig", newline="") as input_file:
        rows = list(csv.DictReader(input_file))
    assert rows[0]["answer_verdict"] == "pending"
    assert rows[0]["citation_filenames"] == "source.md"


def test_answer_batch_records_guards_without_calling_a_model() -> None:
    no_hit_case = RetrievalEvaluationCase(
        id="case-1", question="No evidence?", expected_filenames=["source.md"]
    )
    invalid_citation_case = RetrievalEvaluationCase(
        id="case-2", question="Invalid citation?", expected_filenames=["source.md"]
    )
    results = asyncio.run(
        run_answer_batch(
            uuid4(),
            [no_hit_case, invalid_citation_case],
            FakeRetriever({"No evidence?": [], "Invalid citation?": [make_hit(uuid4())]}),
            FakeService(DeepSeekInvalidCitationError("invalid")),
        )
    )

    assert [result.outcome for result in results] == [
        "retrieval_guard_no_hits",
        "retrieval_guard_invalid_citation",
    ]
