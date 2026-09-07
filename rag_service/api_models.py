from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QueryConstraintsModel(ApiModel):
    source_ids: list[str] = Field(default_factory=list, max_length=100)
    version_ids: list[str] = Field(default_factory=list, max_length=100)


class QueryRequest(ApiModel):
    question: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=200)
    constraints: QueryConstraintsModel = Field(default_factory=QueryConstraintsModel)


class CitationResponse(ApiModel):
    citation_id: str
    source_uri: str
    source_id: str
    document_id: str
    version_id: str
    chunk_id: str
    title: str = ""


class UsageResponse(ApiModel):
    steps: int = 0
    retrieval_attempts: int = 0
    generation_attempts: int = 0
    query_transform_attempts: int = 0
    web_search_attempts: int = 0
    estimated_tokens: int = 0


class QueryResponse(ApiModel):
    request_id: str
    conversation_id: str
    answer: str
    citations: list[CitationResponse] = Field(default_factory=list)
    refusal_reason: str | None = None
    degraded: bool = False
    usage: UsageResponse = Field(default_factory=UsageResponse)
    component_versions: dict[str, str] = Field(default_factory=dict)


class RequestAcceptedResponse(ApiModel):
    request_id: str
    status: str
    status_url: str


class RequestStatusResponse(ApiModel):
    request_id: str
    conversation_id: str
    status: str
    attempt_count: int
    max_attempts: int
    submitted_at_ms: int
    updated_at_ms: int
    completed_at_ms: int | None = None
    error_category: str | None = None
    result: QueryResponse | None = None


class ErrorDetail(ApiModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(ApiModel):
    error: ErrorDetail


class ConversationResponse(ApiModel):
    conversation_id: str
    tenant_id: str
    user_id: str
    updated_at_ms: int
    expires_at_ms: int


class HealthResponse(ApiModel):
    status: Literal["ok", "not_ready"]
    checks: dict[str, str] = Field(default_factory=dict)


class DifyRagRequest(ApiModel):
    query: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = Field(default=None, max_length=200)
    inputs: dict[str, Any] = Field(default_factory=dict)


class DifyRagResponse(ApiModel):
    answer: str
    conversation_id: str
    metadata: dict[str, Any]


class IamIdentityContract(ApiModel):
    tenant_id: str
    user_id: str
    principal_ids: list[str]
    policy_version: str


class CrmActionReference(ApiModel):
    """Reference only: the RAG service does not execute this action."""

    action_type: str
    execution_id: str
    payload_hash: str


class ApprovalReference(ApiModel):
    """Reference only: approval lifecycle remains externally owned."""

    task_id: str
    version: int = Field(ge=1)
    action_hash: str
