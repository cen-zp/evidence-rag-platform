from collections import Counter
from collections.abc import Sequence
from math import log
from uuid import UUID

from app.services.local_hash_embedding import tokenize

BM25_K1 = 1.2
BM25_B = 0.75


def rank_bm25(query: str, documents: Sequence[tuple[UUID, str]]) -> list[UUID]:
    query_tokens = tokenize(query)
    if not query_tokens or not documents:
        return []

    tokenized_documents = [(document_id, tokenize(content)) for document_id, content in documents]
    document_frequency = Counter(
        token for _, tokens in tokenized_documents for token in set(tokens)
    )
    average_length = sum(len(tokens) for _, tokens in tokenized_documents) / len(documents)
    scores: list[tuple[UUID, float]] = []

    for document_id, tokens in tokenized_documents:
        token_frequency = Counter(tokens)
        score = sum(
            _bm25_term_score(
                term_frequency=token_frequency[token],
                document_frequency=document_frequency[token],
                document_count=len(documents),
                document_length=len(tokens),
                average_length=average_length,
            )
            for token in set(query_tokens)
            if token in token_frequency
        )
        if score > 0:
            scores.append((document_id, score))

    ranked_scores = sorted(scores, key=lambda item: item[1], reverse=True)
    return [document_id for document_id, _ in ranked_scores]


def _bm25_term_score(
    term_frequency: int,
    document_frequency: int,
    document_count: int,
    document_length: int,
    average_length: float,
) -> float:
    inverse_document_frequency = log(
        1 + (document_count - document_frequency + 0.5) / (document_frequency + 0.5)
    )
    denominator = term_frequency + BM25_K1 * (
        1 - BM25_B + BM25_B * document_length / average_length
    )
    return inverse_document_frequency * term_frequency * (BM25_K1 + 1) / denominator
