from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
from typing import Any

from rag_service.checkpointing import CheckpointHandle, create_checkpointer
from rag_service.conversation import create_conversation_store
from rag_service.coordination import ConversationCoordinator, create_coordination
from rag_service.execution import ExecutionLimits
from rag_service.resilience import (
    CircuitBreaker,
    ConcurrencyLimiter,
    DependencyGuard,
    RetryPolicy,
    RuntimeResilience,
)
from rag_service.run_store import create_request_run_store
from rag_service.settings import Settings, get_settings
from rag_service.telemetry import RAGTelemetry, create_telemetry


@dataclass
class ApplicationRuntime:
    graph: Any
    checkpoints: CheckpointHandle
    conversations: Any
    coordination: ConversationCoordinator
    settings: Settings
    resilience: RuntimeResilience
    telemetry: RAGTelemetry
    runs: Any = None

    def close(self) -> None:
        with ExitStack() as stack:
            stack.callback(self.checkpoints.close)
            stack.callback(self.coordination.close)
            stack.callback(self.conversations.close)


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
            "graph": active_settings.graph_version,
            "llm": active_settings.llm_model,
            "embedding": active_settings.embedding_model,
            "reranker": active_settings.reranker_model,
        },
        dependency_guards=dependency_guards,
        telemetry=telemetry,
    )


def create_runtime(*, settings: Settings | None = None) -> ApplicationRuntime:
    """Create the configured durable runtime used by the CLI and service adapters."""
    active_settings = settings or get_settings()
    with ExitStack() as resources:
        checkpoints = create_checkpointer(active_settings)
        resources.callback(checkpoints.close)
        conversations = create_conversation_store(active_settings, checkpoints)
        resources.callback(conversations.close)
        runs = create_request_run_store(active_settings, checkpoints)
        coordination, quota = create_coordination(active_settings)
        resources.callback(coordination.close)
        if active_settings.state_backend == "sqlite":
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
            quota=quota,
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
        runtime = ApplicationRuntime(
            graph=graph,
            checkpoints=checkpoints,
            conversations=conversations,
            coordination=coordination,
            settings=active_settings,
            resilience=resilience,
            telemetry=telemetry,
            runs=runs,
        )
        resources.pop_all()
        return runtime
