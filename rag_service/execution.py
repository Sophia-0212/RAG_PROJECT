from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any, Mapping, Sequence

from rag_service.context import ConservativeTokenCounter
from rag_service.retrieval import RetrievalCandidate
from rag_service.settings import Settings, get_settings


class FailureReason(StrEnum):
    DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"  # 整体请求超时（超过request_timeout_seconds）
    STEP_BUDGET_EXCEEDED = "STEP_BUDGET_EXCEEDED"  # Graph总步数用完（超过max_steps）
    RETRIEVAL_BUDGET_EXCEEDED = "RETRIEVAL_BUDGET_EXCEEDED"  # 检索尝试次数用完（超过max_retrieval_attempts）
    GENERATION_BUDGET_EXCEEDED = "GENERATION_BUDGET_EXCEEDED"  # 生成尝试次数用完（超过max_generation_attempts）
    QUERY_REWRITE_EXHAUSTED = "QUERY_REWRITE_EXHAUSTED"  # 查询改写次数用完（超过max_query_transforms）
    WEB_SEARCH_BUDGET_EXCEEDED = "WEB_SEARCH_BUDGET_EXCEEDED"  # 网页搜索次数用完（超过max_web_searches）
    TOKEN_BUDGET_EXCEEDED = "TOKEN_BUDGET_EXCEEDED"  # 累计token用完（超过max_total_tokens）
    NO_PROGRESS = "NO_PROGRESS"  # 原地打转：问题或候选文档重复，没有新进展
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"  # 问题指代不清且无历史上下文，需要用户澄清
    INVALID_REQUEST_CONTEXT = "INVALID_REQUEST_CONTEXT"  # 请求上下文缺失（缺request_id/tenant_id/user_id）
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"  # 没有检索到任何文档，证据不足
    GROUNDING_FAILED = "GROUNDING_FAILED"  # 生成的答案没有被检索到的文档支撑（幻觉判定）
    ANSWER_NOT_USEFUL = "ANSWER_NOT_USEFUL"  # 生成的答案被判定为对问题没有帮助
    ROUTE_NOT_SUPPORTED = "ROUTE_NOT_SUPPORTED"  # 问题路由判定为当前不支持的类型
    POLICY_EXHAUSTED = "POLICY_EXHAUSTED"  # 兜底原因：以上都不是，但流程走到了终点仍未产出结果


class Action(StrEnum):
    ROUTE = "route"
    RETRIEVE = "retrieve"
    GENERATE = "generate"
    TRANSFORM_QUERY = "transform_query"
    WEB_SEARCH = "web_search"
    DIRECT_ANSWER = "direct_answer"
    GRADE_DOCUMENTS = "grade_documents"
    GRADE_GENERATION = "grade_generation"


@dataclass(frozen=True)
class ExecutionLimits:
    max_steps: int = 16  # 单轮请求Graph总步数上限，不区分动作类型，累计到此强制停止
    max_retrieval_attempts: int = 3  # 单轮请求内，检索动作最多允许执行几次
    max_generation_attempts: int = 3  # 单轮请求内，生成/直接回答动作最多允许执行几次
    max_query_transforms: int = 2  # 单轮请求内，查询改写最多允许几次
    max_web_searches: int = 1  # 单轮请求内，网页搜索最多允许几次
    max_total_tokens: int = 8192  # 单轮请求累计消耗的token上限（喂给LLM+LLM生成的内容总和）
    request_timeout_seconds: float = 30.0  # 单轮请求从开始到必须完成的总时限（秒）

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "ExecutionLimits":
        active = settings or get_settings()
        return cls(
            max_steps=active.max_steps,
            max_retrieval_attempts=active.max_retrieval_attempts,
            max_generation_attempts=active.max_generation_attempts,
            max_query_transforms=active.max_query_transforms,
            max_web_searches=active.max_web_searches,
            max_total_tokens=active.max_total_tokens,
            request_timeout_seconds=active.request_timeout_seconds,
        )

    @classmethod
    def from_value(cls, value: Mapping[str, Any] | None) -> "ExecutionLimits":
        if not value:
            return cls.from_settings()
        return cls(**{field: value[field] for field in asdict(cls()) if field in value})

    def to_dict(self) -> dict[str, int | float]:
        return asdict(self)


_ACTION_COUNTER = {
    Action.RETRIEVE: ("retrieval_attempts", "max_retrieval_attempts", FailureReason.RETRIEVAL_BUDGET_EXCEEDED),
    Action.GENERATE: ("generation_attempts", "max_generation_attempts", FailureReason.GENERATION_BUDGET_EXCEEDED),
    Action.TRANSFORM_QUERY: ("query_transform_attempts", "max_query_transforms", FailureReason.QUERY_REWRITE_EXHAUSTED),
    Action.WEB_SEARCH: ("web_search_attempts", "max_web_searches", FailureReason.WEB_SEARCH_BUDGET_EXCEEDED),
    Action.DIRECT_ANSWER: ("generation_attempts", "max_generation_attempts", FailureReason.GENERATION_BUDGET_EXCEEDED),
}


def _now_ms() -> int:
    return int(time.time() * 1000)


def initialize_execution(
    state: Mapping[str, Any],
    limits: ExecutionLimits,
    *,
    now_ms: int | None = None,
    component_versions: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Reset request-scoped execution state while retaining conversation metadata."""
    current_ms = _now_ms() if now_ms is None else now_ms
    question = str(state.get("question", "")).strip()
    request_context = dict(state.get("request_context") or {})
    request_id = str(request_context.get("request_id", ""))
    previous_request_id = str(state.get("active_request_id", ""))
    if request_id and request_id == previous_request_id and state.get("started_at_ms"):
        return {}
    updates = {
        "active_request_id": request_id,
        "original_question": question,
        "question": question,
        "query_history": [question] if question else [],
        "query_fingerprints": [query_fingerprint(question)] if question else [],
        "candidate_fingerprints": [],
        "retrieval_repeated": False,
        "step_count": 0,
        "retrieval_attempts": 0,
        "generation_attempts": 0,
        "query_transform_attempts": 0,
        "web_search_attempts": 0,
        "token_count": 0,
        "started_at_ms": current_ms,
        "deadline_at_ms": current_ms + int(limits.request_timeout_seconds * 1000),
        "execution_limits": limits.to_dict(),
        "failure_reason": None,
        "generation_grade": None,
        "evidence_source": None,
        "documents": [],
        "candidates": [],
        "parent_documents": {},
        "generation": "",
        "answer_result": {},
        "context_pack": None,
        "component_versions": dict(component_versions or {}),
    }
    if needs_clarification(question, str(state.get("conversation_summary", ""))):
        updates["failure_reason"] = FailureReason.CLARIFICATION_REQUIRED.value
    required_context = ("request_id", "tenant_id", "user_id")
    if any(not str(request_context.get(field, "")).strip() for field in required_context):
        updates["failure_reason"] = FailureReason.INVALID_REQUEST_CONTEXT.value
    return updates


def budget_failure(
    state: Mapping[str, Any],
    *,
    action: Action | None = None,
    now_ms: int | None = None,
) -> FailureReason | None:
    existing = state.get("failure_reason")
    if existing:
        return FailureReason(str(existing))
    limits = ExecutionLimits.from_value(state.get("execution_limits"))
    current_ms = _now_ms() if now_ms is None else now_ms
    deadline = int(state.get("deadline_at_ms", 0) or 0)
    if deadline and current_ms >= deadline:
        return FailureReason.DEADLINE_EXCEEDED
    if int(state.get("step_count", 0)) >= limits.max_steps:
        return FailureReason.STEP_BUDGET_EXCEEDED
    if int(state.get("token_count", 0)) >= limits.max_total_tokens:
        return FailureReason.TOKEN_BUDGET_EXCEEDED
    if action in _ACTION_COUNTER:
        counter, limit_name, reason = _ACTION_COUNTER[action]
        if int(state.get(counter, 0)) >= int(getattr(limits, limit_name)):
            return reason
    return None


def begin_action(
    state: Mapping[str, Any],
    action: Action,
    *,
    now_ms: int | None = None,
) -> tuple[bool, dict[str, Any]]:
    failure = budget_failure(state, action=action, now_ms=now_ms)
    if failure:
        return False, {"failure_reason": failure.value}
    updates: dict[str, Any] = {
        "step_count": int(state.get("step_count", 0)) + 1,
        "last_action": action.value,
    }
    action_counter = _ACTION_COUNTER.get(action)
    if action_counter:
        counter, _, _ = action_counter
        updates[counter] = int(state.get(counter, 0)) + 1
    return True, updates


def record_token_usage(state: Mapping[str, Any], *texts: str, additional_tokens: int = 0) -> dict[str, Any]:
    counter = ConservativeTokenCounter()
    used = int(state.get("token_count", 0)) + additional_tokens
    used += sum(counter.count(text) for text in texts)
    updates: dict[str, Any] = {"token_count": used}
    limits = ExecutionLimits.from_value(state.get("execution_limits"))
    if used > limits.max_total_tokens:
        updates["failure_reason"] = FailureReason.TOKEN_BUDGET_EXCEEDED.value
    return updates


def query_fingerprint(query: str) -> str:
    normalized = re.sub(r"\s+", " ", query.strip().casefold())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def needs_clarification(question: str, conversation_summary: str) -> bool:
    """Fail closed for pronoun-only follow-ups when no prior context is available."""
    if conversation_summary.strip():
        return False
    normalized = re.sub(r"\s+", "", question.strip().casefold())
    ambiguous_prefixes = ("这个", "那个", "它", "上述", "前面", "这件事", "那件事")
    return len(normalized) <= 20 and normalized.startswith(ambiguous_prefixes)


def record_query(state: Mapping[str, Any], query: str) -> dict[str, Any]:
    fingerprint = query_fingerprint(query)
    fingerprints = list(state.get("query_fingerprints") or [])
    history = list(state.get("query_history") or [])
    if not query.strip() or fingerprint in fingerprints:
        return {
            "failure_reason": FailureReason.NO_PROGRESS.value,
            "query_history": history,
            "query_fingerprints": fingerprints,
        }
    history.append(query)
    fingerprints.append(fingerprint)
    return {"query_history": history, "query_fingerprints": fingerprints}


def candidate_fingerprint(candidates: Sequence[RetrievalCandidate]) -> str:
    identities = sorted(f"{candidate.version_id}:{candidate.chunk_id}" for candidate in candidates)
    payload = json.dumps(identities, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def record_candidates(state: Mapping[str, Any], candidates: Sequence[RetrievalCandidate]) -> dict[str, Any]:
    fingerprint = candidate_fingerprint(candidates)
    fingerprints = list(state.get("candidate_fingerprints") or [])
    repeated = fingerprint in fingerprints
    fingerprints.append(fingerprint)
    return {
        "candidate_fingerprints": fingerprints,
        "retrieval_repeated": repeated,
    }


def terminal_reason(state: Mapping[str, Any]) -> FailureReason:
    existing = state.get("failure_reason")
    if existing:
        return FailureReason(str(existing))
    if state.get("retrieval_repeated") and not state.get("documents"):
        return FailureReason.NO_PROGRESS
    if state.get("route_supported") is False:
        return FailureReason.ROUTE_NOT_SUPPORTED
    grade = state.get("generation_grade")
    if grade == "not_supported":
        return FailureReason.GROUNDING_FAILED
    if grade == "not_useful":
        return FailureReason.ANSWER_NOT_USEFUL
    if not state.get("documents"):
        return FailureReason.INSUFFICIENT_EVIDENCE
    return FailureReason.POLICY_EXHAUSTED
