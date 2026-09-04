from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rag_service.checkpointing import CheckpointHandle, create_sqlite_checkpointer
from rag_service.conversation import ConversationStore
from rag_service.execution import ExecutionLimits
from rag_service.resilience import (
    CircuitBreaker,
    ConcurrencyLimiter,
    DependencyGuard,
    RetryPolicy,
    RuntimeResilience,
    TenantTokenBucket,
)
from rag_service.settings import Settings, get_settings
from rag_service.telemetry import RAGTelemetry, create_telemetry


@dataclass
class ApplicationRuntime:
    graph: Any
    checkpoints: CheckpointHandle
    conversations: ConversationStore
    settings: Settings
    resilience: RuntimeResilience
    telemetry: RAGTelemetry

    def close(self) -> None:
        self.conversations.close()
        self.checkpoints.close()


def create_graph(
    *,
    checkpointer=None,
    settings: Settings | None = None,
    dependency_guards=None,
    telemetry: RAGTelemetry | None = None,
) -> Any:
    """Create the canonical Graph 2 workflow without running it."""
    from graph2.graph_2 import build_graph

    active_settings = settings or get_settings()
    return build_graph(
        checkpointer=checkpointer,
        limits=ExecutionLimits.from_settings(active_settings),
        component_versions={
            "graph": "graph2-bounded-v1",
            "llm": active_settings.llm_model,
            "embedding": active_settings.embedding_model,
            "reranker": active_settings.reranker_model,
        },
        dependency_guards=dependency_guards,
        telemetry=telemetry,
    )


def create_runtime(*, settings: Settings | None = None) -> ApplicationRuntime:
    """Create the durable local runtime used by the CLI and service adapters."""
    active_settings = settings or get_settings()
    checkpoints = create_sqlite_checkpointer(active_settings.checkpoint_path)
    conversations = ConversationStore(active_settings.checkpoint_path)
    conversations.prune_expired(checkpoints.saver)
    retry_policy = RetryPolicy(
        max_attempts=active_settings.dependency_max_attempts,
        initial_backoff_seconds=active_settings.dependency_retry_initial_seconds,
        max_backoff_seconds=active_settings.dependency_retry_max_seconds,
    )
    dependency_guards = {
        name: DependencyGuard(
            CircuitBreaker(
                failure_threshold=active_settings.circuit_failure_threshold,
                recovery_timeout_seconds=active_settings.circuit_recovery_seconds,
            ),
            retry_policy,
        )
        for name in ("retrieval", "web_search", "llm")
    }
    resilience = RuntimeResilience(
        quota=TenantTokenBucket(
            capacity=active_settings.tenant_request_burst,
            refill_per_second=active_settings.tenant_requests_per_minute / 60,
        ),
        concurrency=ConcurrencyLimiter(
            capacity=active_settings.max_concurrent_requests,
            acquire_timeout_seconds=active_settings.concurrency_acquire_timeout_seconds,
        ),
        dependency_guards=dependency_guards,
    )
    telemetry = create_telemetry()
    graph = create_graph(
        checkpointer=checkpoints.saver,
        settings=active_settings,
        dependency_guards=dependency_guards,
        telemetry=telemetry,
    )
    return ApplicationRuntime(
        graph=graph,
        checkpoints=checkpoints,
        conversations=conversations,
        settings=active_settings,
        resilience=resilience,
        telemetry=telemetry,
    )
