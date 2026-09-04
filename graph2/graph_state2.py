from __future__ import annotations

from typing import Any, TypedDict

from langchain_core.documents import Document

from rag_service.retrieval import RetrievalCandidate


class GraphState(TypedDict, total=False):
    question: str
    original_question: str
    active_request_id: str
    request_context: dict[str, Any]
    query_constraints: dict[str, Any]
    conversation_summary: str
    query_history: list[str]
    query_fingerprints: list[str]
    candidate_fingerprints: list[str]
    retrieval_repeated: bool
    execution_limits: dict[str, int | float]
    step_count: int
    retrieval_attempts: int
    generation_attempts: int
    query_transform_attempts: int
    web_search_attempts: int
    token_count: int
    started_at_ms: int
    deadline_at_ms: int
    last_action: str
    failure_reason: str | None
    generation_grade: str | None
    evidence_source: str | None
    route_supported: bool
    question_route: str
    component_versions: dict[str, str]
    transform_count: int
    hallucination_count: int
    generation: str
    documents: list[Document]
    candidates: list[RetrievalCandidate]
    retrieval_filter: str
    retrieval_degraded: bool
    degradation_reason: str | None
    context_pack: Any
    parent_documents: dict[str, Document]
    answer_result: dict[str, Any]
