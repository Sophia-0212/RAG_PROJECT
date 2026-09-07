from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest


_TRACE_FIELDS = frozenset(
    {
        "request_id",  # 请求唯一标识
        "tenant_hash",  # 租户ID的哈希值（脱敏后，不是原始tenant_id）
        "user_hash",  # 用户ID的哈希值（脱敏后，不是原始user_id）
        "conversation_hash",  # 会话ID的哈希值（脱敏后）
        "action",  # 当前执行的动作类型（route/retrieve/generate等，对应Action枚举）
        "outcome",  # 结果（success/refused/error等）
        "reason",  # 拒绝或失败的具体原因
        "route",  # 问题路由到了哪条分支（web_search/vectorstore/direct_answer）
        "degraded",  # 是否降级返回（未完全满足质量要求但仍返回了结果）
        "elapsed_ms",  # 耗时（毫秒）
        "step_count",  # 本轮请求Graph总步数
        "retrieval_attempts",  # 本轮请求检索尝试次数
        "generation_attempts",  # 本轮请求生成尝试次数
        "estimated_tokens",  # 本轮请求估算的token消耗
        "component_versions",  # 本次用到的模型/组件版本信息
        "candidate_ids",  # 检索候选文档的chunk_id列表
        "candidate_scores",  # 检索候选文档的分数列表
        "citation_ids",  # 生成答案引用的citation标识列表
        "cited_chunk_ids",  # 生成答案引用的chunk_id列表
        "run_status",  # 请求执行运行状态（用于持久化运行生命周期跟踪）
        "attempt_count",  # 整体请求重试次数（区别于单个动作的attempts）
        "lease_owner_hash",  # 分布式协调中持有租约的所有者标识哈希（脱敏后）
    }
)


def hash_identifier(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def redact_attributes(attributes: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in attributes.items() if key in _TRACE_FIELDS}


class EventSink(Protocol):
    def emit(self, event: Mapping[str, Any]) -> None: ...


class JsonLogSink:
    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger("rag.telemetry")

    def emit(self, event: Mapping[str, Any]) -> None:
        self.logger.info(json.dumps(dict(event), ensure_ascii=True, separators=(",", ":"), sort_keys=True))


class MemoryEventSink:
    def __init__(self):
        self.events: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def emit(self, event: Mapping[str, Any]) -> None:
        with self._lock:
            self.events.append(dict(event))


@dataclass
class RAGTelemetry:
    sink: EventSink

    def __post_init__(self) -> None:
        self.registry = CollectorRegistry(auto_describe=True)
        self.requests = Counter(
            "rag_requests_total",
            "Completed RAG requests",
            ("outcome", "reason", "degraded"),
            registry=self.registry,
        )
        self.duration = Histogram(
            "rag_request_duration_seconds",
            "RAG request duration",
            ("outcome",),
            registry=self.registry,
        )
        self.in_flight = Gauge(
            "rag_requests_in_flight",
            "Current RAG requests",
            registry=self.registry,
        )
        self.rejections = Counter(
            "rag_request_rejections_total",
            "Requests rejected before workflow execution",
            ("reason",),
            registry=self.registry,
        )
        self.action_duration = Histogram(
            "rag_graph_action_duration_seconds",
            "Graph action duration",
            ("action", "outcome"),
            registry=self.registry,
        )
        self.coordination_events = Counter(
            "rag_coordination_events_total",
            "Distributed coordination outcomes",
            ("action", "outcome"),
            registry=self.registry,
        )
        self.run_events = Counter(
            "rag_run_events_total",
            "Durable request-run lifecycle outcomes",
            ("action", "outcome"),
            registry=self.registry,
        )
        self.recovery_backlog = Gauge(
            "rag_recovery_backlog",
            "Recoverable request runs waiting or holding an expired lease",
            registry=self.registry,
        )
        self.recovery_backlog_oldest_seconds = Gauge(
            "rag_recovery_backlog_oldest_seconds",
            "Age of the oldest recoverable request run",
            registry=self.registry,
        )
        self.dependency_ready = Gauge(
            "rag_dependency_ready",
            "Whether a required runtime dependency is ready",
            ("dependency",),
            registry=self.registry,
        )

    def trace(self, name: str, attributes: Mapping[str, Any]) -> None:
        self.sink.emit({"event": name, **redact_attributes(attributes)})

    def observe_request(self, *, elapsed_seconds: float, response: Mapping[str, Any]) -> None:
        reason = str(response.get("refusal_reason") or "none")
        outcome = "refused" if response.get("refusal_reason") else "success"
        degraded = "true" if response.get("degraded") else "false"
        self.requests.labels(outcome=outcome, reason=reason, degraded=degraded).inc()
        self.duration.labels(outcome=outcome).observe(elapsed_seconds)

    def observe_action(self, *, action: str, outcome: str, elapsed_seconds: float) -> None:
        self.action_duration.labels(action=action, outcome=outcome).observe(elapsed_seconds)

    def observe_coordination(self, *, action: str, outcome: str) -> None:
        self.coordination_events.labels(action=action, outcome=outcome).inc()

    def observe_run(self, *, action: str, outcome: str) -> None:
        self.run_events.labels(action=action, outcome=outcome).inc()

    def set_recovery_backlog(self, *, count: int, oldest_age_seconds: float) -> None:
        self.recovery_backlog.set(count)
        self.recovery_backlog_oldest_seconds.set(oldest_age_seconds)

    def set_dependency_ready(self, dependency: str, ready: bool) -> None:
        self.dependency_ready.labels(dependency=dependency).set(1 if ready else 0)

    def metrics(self) -> bytes:
        return generate_latest(self.registry)


def create_telemetry(sink: EventSink | None = None) -> RAGTelemetry:
    return RAGTelemetry(sink=sink or JsonLogSink())
