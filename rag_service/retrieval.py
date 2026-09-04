from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from typing import Iterable, Sequence

from langchain_core.documents import Document

from rag_service.security import RequestContext, is_document_authorized


@dataclass(frozen=True)
class RetrievalCandidate:
    document: Document
    recall_rank: int
    fused_score: float | None = None
    rerank_score: float | None = None

    @property
    def chunk_id(self) -> str:
        value = self.document.metadata.get("chunk_id")
        if value:
            return str(value)
        return hashlib.sha256(self.document.page_content.encode("utf-8")).hexdigest()

    @property
    def version_id(self) -> str:
        return str(self.document.metadata.get("version_id", ""))


def candidates_from_documents(documents: Sequence[Document]) -> list[RetrievalCandidate]:
    candidates = []
    for rank, document in enumerate(documents, start=1):
        raw_score = document.metadata.get("fused_score", document.metadata.get("score"))
        score = float(raw_score) if isinstance(raw_score, (int, float)) else None
        candidates.append(
            RetrievalCandidate(
                document=document,
                recall_rank=rank,
                fused_score=score,
            )
        )
    return candidates


def authorize_candidates(
    candidates: Iterable[RetrievalCandidate],
    context: RequestContext,
) -> list[RetrievalCandidate]:
    return [candidate for candidate in candidates if is_document_authorized(candidate.document, context)]


def deduplicate_candidates(candidates: Iterable[RetrievalCandidate]) -> list[RetrievalCandidate]:
    best: dict[str, RetrievalCandidate] = {}
    for candidate in candidates:
        current = best.get(candidate.chunk_id)
        if current is None:
            best[candidate.chunk_id] = candidate
            continue
        current_score = current.rerank_score if current.rerank_score is not None else current.fused_score
        candidate_score = candidate.rerank_score if candidate.rerank_score is not None else candidate.fused_score
        if candidate_score is not None and (current_score is None or candidate_score > current_score):
            best[candidate.chunk_id] = candidate
    return sorted(best.values(), key=lambda item: item.recall_rank)


def with_rerank_scores(
    candidates: Sequence[RetrievalCandidate],
    scores: Sequence[float],
) -> list[RetrievalCandidate]:
    if len(candidates) != len(scores):
        raise ValueError("rerank scores must align with candidates")
    scored = [replace(candidate, rerank_score=float(score)) for candidate, score in zip(candidates, scores)]
    return sorted(scored, key=lambda item: item.rerank_score, reverse=True)
