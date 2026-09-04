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
        "request_id",
        "tenant_hash",
        "user_hash",
        "conversation_hash",
        "action",
        "outcome",
        "reason",
        "route",
        "degraded",
        "elapsed_ms",
        "step_count",
        "retrieval_attempts",
        "generation_attempts",
        "estimated_tokens",
        "component_versions",
        "candidate_ids",
        "candidate_scores",
        "citation_ids",
        "cited_chunk_ids",
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

    def metrics(self) -> bytes:
        return generate_latest(self.registry)


def create_telemetry(sink: EventSink | None = None) -> RAGTelemetry:
    return RAGTelemetry(sink=sink or JsonLogSink())
