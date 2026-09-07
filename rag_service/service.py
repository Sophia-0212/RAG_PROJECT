from __future__ import annotations

import hashlib
import os
import socket
import time
from collections.abc import Iterator, Mapping
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from rag_service.application import ApplicationRuntime
from rag_service.auth import IdentityClaims
from rag_service.auth import (
    RecoveryAuthorizationDenied,
    RecoveryAuthorizationError,
    RecoveryAuthorizationUnavailable,
    RecoveryIdentityResolver,
)
from rag_service.conversation import ConversationRecord, scoped_thread_id
from rag_service.coordination import (
    ConversationBusyError,
    CoordinationUnavailableError,
    LocalConversationCoordinator,
)
from rag_service.resilience import CapacityExceededError, QuotaExceededError
from rag_service.run_store import (
    RequestRun,
    RunLeaseHeartbeat,
    RunLeaseLostError,
    RunStatus,
)
from rag_service.telemetry import hash_identifier


class ServiceExecutionError(RuntimeError):
    """Raised when an internal dependency prevents request completion."""
    # 内部依赖（Graph执行/检索/生成等）出错导致这次请求跑不完，兜底异常


class RequestPendingError(RuntimeError):
    # 这个请求当前正被别的地方占用/处理中（比如租约被别人持有），暂时无法处理，客户端该稍后重试
    def __init__(self, request_id: str, status: RunStatus):
        super().__init__("request is still being processed")
        self.request_id = request_id
        self.status = status


class RequestTerminalError(RuntimeError):
    # 这个请求已经到达终态（失败/取消/过期），不会再被处理，报错时附带具体的终态和失败分类
    def __init__(self, request_id: str, status: RunStatus, error_category: str | None):
        super().__init__("request reached a terminal state")
        self.request_id = request_id
        self.status = status
        self.error_category = error_category


class IncompatibleRunError(RuntimeError):
    """A checkpoint cannot be resumed by the active graph/input schema."""
    # 存量checkpoint的Graph版本/输入结构，跟当前代码的版本不兼容，不能安全恢复继续执行


@dataclass(frozen=True)
class QueryCommand:
    question: str  # 用户问的问题原文，比如"退货政策是什么"
    conversation_id: str  # 会话id，标识这是哪一轮对话，用于关联历史上下文
    request_id: str  # 请求id，标识这一次具体的调用，用于幂等去重和日志追踪
    constraints: Mapping[str, Any]  # 查询约束条件（可选，比如过滤某个产品线/文档范围）


class RAGService:
    def __init__(self, runtime: ApplicationRuntime):
        self.runtime = runtime
        self.resilience = getattr(runtime, "resilience", None)
        self.telemetry = getattr(runtime, "telemetry", None)
        self.coordination = getattr(runtime, "coordination", None) or LocalConversationCoordinator()
        self.runs = getattr(runtime, "runs", None)
        self._owner_id = f"api:{socket.gethostname()}:{os.getpid()}:{uuid4()}"

    @property
    def durable_recovery_enabled(self) -> bool:
        return bool(self.runs is not None and self.runtime.settings.recovery_enabled)

    def _claim(self, command: QueryCommand, identity: IdentityClaims) -> ConversationRecord:
        return self.runtime.conversations.claim(
            command.conversation_id,
            tenant_id=identity.tenant_id,
            user_id=identity.user_id,
            ttl_seconds=self.runtime.settings.conversation_ttl_seconds,
        )

    @staticmethod
    def _inputs(command: QueryCommand, identity: IdentityClaims, record: ConversationRecord) -> dict[str, Any]:
        return {
            "question": command.question,
            "conversation_summary": record.summary,
            "query_constraints": dict(command.constraints),
            "request_context": {
                "request_id": command.request_id,
                "tenant_id": identity.tenant_id,
                "user_id": identity.user_id,
                "principal_ids": identity.principal_ids,
            },
        }

    def _config(
        self,
        command: QueryCommand,
        record: ConversationRecord,
        run: RequestRun | None = None,
    ) -> dict[str, Any]:
        return {
            "configurable": {"thread_id": run.thread_id if run else record.thread_id},
            "recursion_limit": self.runtime.settings.max_steps + 8,
            "metadata": {
                "request_id": command.request_id,
                "conversation_id": command.conversation_id,
                "tenant_id": record.tenant_id,
            },
        }

    @staticmethod
    def _response(command: QueryCommand, state: Mapping[str, Any]) -> dict[str, Any]:
        answer_result = dict(state.get("answer_result") or {})
        return {
            "request_id": command.request_id,
            "conversation_id": command.conversation_id,
            "answer": str(answer_result.get("answer", state.get("generation", ""))),
            "citations": list(answer_result.get("citations") or []),
            "refusal_reason": answer_result.get("refusal_reason"),
            "degraded": bool(answer_result.get("degraded", False)),
            "usage": {
                "steps": int(state.get("step_count", 0)),
                "retrieval_attempts": int(state.get("retrieval_attempts", 0)),
                "generation_attempts": int(state.get("generation_attempts", 0)),
                "query_transform_attempts": int(state.get("query_transform_attempts", 0)),
                "web_search_attempts": int(state.get("web_search_attempts", 0)),
                "estimated_tokens": int(state.get("token_count", 0)),
            },
            "component_versions": dict(state.get("component_versions") or {}),
        }

    def _remember(self, command: QueryCommand, identity: IdentityClaims, response: Mapping[str, Any]) -> None:
        self.runtime.conversations.append_turn(
            command.conversation_id,
            tenant_id=identity.tenant_id,
            user_id=identity.user_id,
            question=command.question,
            answer=str(response["answer"]),
            ttl_seconds=self.runtime.settings.conversation_ttl_seconds,
            max_chars=self.runtime.settings.conversation_summary_max_chars,
        )

    def _raise_for_terminal(self, run: RequestRun) -> None:
        if run.status == RunStatus.SUCCEEDED and run.result is not None:
            return
        if run.status in {
            RunStatus.FAILED_TERMINAL,
            RunStatus.CANCELLED,
            RunStatus.EXPIRED,
        }:
            raise RequestTerminalError(run.request_id, run.status, run.error_category)

    def _submit_run(
        self,
        command: QueryCommand,
        identity: IdentityClaims,
        record: ConversationRecord,
    ) -> RequestRun:
        run, created = self.runs.submit(
            tenant_id=identity.tenant_id,
            request_id=command.request_id,
            conversation_id=command.conversation_id,
            user_id=identity.user_id,
            question=command.question,
            constraints=command.constraints,
            graph_version=self.runtime.settings.graph_version,
            input_schema_version=self.runtime.settings.input_schema_version,
            max_attempts=self.runtime.settings.recovery_max_attempts,
            recovery_window_seconds=self.runtime.settings.recovery_window_seconds,
            initial_recovery_delay_seconds=self.runtime.settings.run_lease_seconds,
        )
        if self.telemetry:
            self.telemetry.observe_run(
                action="submit",
                outcome="created" if created else "duplicate",
            )
            self.telemetry.trace(
                "run_submitted",
                {
                    "request_id": command.request_id,
                    "tenant_hash": hash_identifier(identity.tenant_id),
                    "conversation_hash": hash_identifier(command.conversation_id),
                    "run_status": run.status.value,
                    "attempt_count": run.attempt_count,
                },
            )
        return run

    @staticmethod
    def _command_from_run(run: RequestRun) -> QueryCommand:
        return QueryCommand(
            question=str(run.request_payload.get("question", "")),
            conversation_id=run.conversation_id,
            request_id=run.request_id,
            constraints=dict(run.request_payload.get("constraints") or {}),
        )

    def _retry_delay(self, run: RequestRun) -> float:
        base_delay = float(2 ** max(0, run.attempt_count - 1))
        digest = hashlib.sha256(
            f"{run.request_id}:{run.attempt_count}".encode("utf-8")
        ).digest()
        jitter = 0.8 + (digest[0] / 255.0) * 0.4
        return min(30.0, base_delay * jitter)

    def _mark_retryable(self, run: RequestRun, category: str) -> None:
        try:
            self.runs.mark_retryable(
                run,
                error_category=category,
                retry_delay_seconds=self._retry_delay(run),
            )
        except RunLeaseLostError:
            return

    def _validated_snapshot(self, run: RequestRun, config: Mapping[str, Any]):
        if run.graph_version != self.runtime.settings.graph_version:
            raise IncompatibleRunError("graph version is incompatible")
        if run.input_schema_version != self.runtime.settings.input_schema_version:
            raise IncompatibleRunError("input schema version is incompatible")
        snapshot = self.runtime.graph.get_state(config)
        state = dict(snapshot.values or {})
        if state:
            context = dict(state.get("request_context") or {})
            if not context or (
                str(context.get("request_id", "")) != run.request_id
                or str(context.get("tenant_id", "")) != run.tenant_id
                or str(context.get("user_id", "")) != run.user_id
            ):
                raise IncompatibleRunError("checkpoint request context does not match the run ledger")
            checkpoint_graph = str((state.get("component_versions") or {}).get("graph", ""))
            if checkpoint_graph and checkpoint_graph != run.graph_version:
                raise IncompatibleRunError("checkpoint graph version is incompatible")
        return snapshot

    def _execute_claimed(
        self,
        run: RequestRun,
        command: QueryCommand,
        identity: IdentityClaims,
        record: ConversationRecord,
    ) -> dict[str, Any]:
        config = self._config(command, record, run)
        with RunLeaseHeartbeat(
            self.runs,
            run,
            lease_seconds=self.runtime.settings.run_lease_seconds,
            interval_seconds=self.runtime.settings.run_heartbeat_seconds,
        ) as heartbeat:
            snapshot = self._validated_snapshot(run, config)
            if not snapshot.values:
                state = self.runtime.graph.invoke(
                    self._inputs(command, identity, record),
                    config=config,
                    durability="sync",
                )
            elif snapshot.next:
                self.runtime.graph.update_state(
                    config,
                    {
                        "deadline_at_ms": int(time.time() * 1000)
                        + int(self.runtime.settings.request_timeout_seconds * 1000)
                    },
                )
                state = self.runtime.graph.invoke(None, config=config, durability="sync")
            else:
                state = snapshot.values
            if heartbeat.lost:
                raise RunLeaseLostError("run lease heartbeat was lost")
            response = self._response(command, state)
            self.runs.finalize(
                run,
                response=response,
                question=command.question,
                conversation_ttl_seconds=self.runtime.settings.conversation_ttl_seconds,
                summary_max_chars=self.runtime.settings.conversation_summary_max_chars,
            )
            if self.telemetry:
                self.telemetry.observe_run(action="finalize", outcome="success")
                self.telemetry.trace(
                    "run_finalized",
                    {
                        "request_id": run.request_id,
                        "tenant_hash": hash_identifier(run.tenant_id),
                        "run_status": RunStatus.SUCCEEDED.value,
                        "attempt_count": run.attempt_count,
                    },
                )
        return response

    def _query_durable(self, command: QueryCommand, identity: IdentityClaims) -> dict[str, Any]:
        record = self._claim(command, identity)
        run = self._submit_run(command, identity, record)
        if run.status == RunStatus.SUCCEEDED and run.result is not None:
            return run.result
        self._raise_for_terminal(run)
        claimed = self.runs.claim(
            identity.tenant_id,
            command.request_id,
            owner=self._owner_id,
            lease_seconds=self.runtime.settings.run_lease_seconds,
        )
        if claimed is None:
            current = self.runs.get(identity.tenant_id, command.request_id) or run
            if current.status == RunStatus.SUCCEEDED and current.result is not None:
                return current.result
            self._raise_for_terminal(current)
            raise RequestPendingError(command.request_id, current.status)
        if self.telemetry:
            self.telemetry.observe_run(action="claim", outcome="success")
        try:
            with self.coordination.slot(record.thread_id):
                return self._execute_claimed(claimed, command, identity, record)
        except IncompatibleRunError:
            self.runs.mark_terminal(
                claimed,
                status=RunStatus.FAILED_TERMINAL,
                error_category="INCOMPATIBLE_GRAPH_VERSION",
            )
            raise RequestTerminalError(
                claimed.request_id,
                RunStatus.FAILED_TERMINAL,
                "INCOMPATIBLE_GRAPH_VERSION",
            )
        except (ConversationBusyError, CoordinationUnavailableError):
            self._mark_retryable(claimed, "COORDINATION_UNAVAILABLE")
            raise
        except RunLeaseLostError:
            raise RequestPendingError(claimed.request_id, RunStatus.RUNNING)
        except Exception as exc:
            self._mark_retryable(claimed, "EXECUTION_FAILED")
            raise ServiceExecutionError("RAG workflow execution failed") from exc

    def recover_next(self, resolver: RecoveryIdentityResolver, *, owner: str) -> bool:
        if not self.durable_recovery_enabled:
            return False
        self.runs.reconcile_expired()
        run = self.runs.claim_next(
            owner=owner,
            lease_seconds=self.runtime.settings.run_lease_seconds,
        )
        if run is None:
            return False
        if self.telemetry:
            self.telemetry.observe_run(action="recovery_claim", outcome="success")
            self.telemetry.trace(
                "run_recovery_claimed",
                {
                    "request_id": run.request_id,
                    "tenant_hash": hash_identifier(run.tenant_id),
                    "run_status": run.status.value,
                    "attempt_count": run.attempt_count,
                    "lease_owner_hash": hash_identifier(owner),
                },
            )
        try:
            identity = resolver.resolve(
                tenant_id=run.tenant_id,
                user_id=run.user_id,
                request_id=run.request_id,
            )
            if identity.tenant_id != run.tenant_id or identity.user_id != run.user_id:
                raise RecoveryAuthorizationDenied("recovery identity mismatch")
            command = self._command_from_run(run)
            record = self.runtime.conversations.get(
                run.conversation_id,
                tenant_id=run.tenant_id,
                user_id=run.user_id,
            )
            capacity = self.resilience.concurrency.slot() if self.resilience else nullcontext()
            with capacity, self.coordination.slot(record.thread_id):
                self._execute_claimed(run, command, identity, record)
            if self.telemetry:
                self.telemetry.observe_run(action="recovery", outcome="success")
            return True
        except RecoveryAuthorizationDenied:
            self.runs.mark_terminal(
                run,
                status=RunStatus.FAILED_TERMINAL,
                error_category="RECOVERY_AUTHORIZATION_DENIED",
            )
            if self.telemetry:
                self.telemetry.observe_run(action="recovery", outcome="authorization_denied")
            return True
        except RecoveryAuthorizationUnavailable:
            self._mark_retryable(run, "RECOVERY_AUTHORIZATION_UNAVAILABLE")
            if self.telemetry:
                self.telemetry.observe_run(action="recovery", outcome="authorization_unavailable")
            return True
        except RecoveryAuthorizationError:
            self._mark_retryable(run, "RECOVERY_AUTHORIZATION_UNAVAILABLE")
            return True
        except IncompatibleRunError:
            self.runs.mark_terminal(
                run,
                status=RunStatus.FAILED_TERMINAL,
                error_category="INCOMPATIBLE_GRAPH_VERSION",
            )
            if self.telemetry:
                self.telemetry.observe_run(action="recovery", outcome="incompatible_version")
            return True
        except RunLeaseLostError:
            return True
        except Exception:
            self._mark_retryable(run, "RECOVERY_ATTEMPT_FAILED")
            if self.telemetry:
                self.telemetry.observe_run(action="recovery", outcome="retryable_failure")
            return True

    def query(self, command: QueryCommand, identity: IdentityClaims) -> dict[str, Any]:
        started = time.perf_counter()
        if self.resilience:
            try:
                self.resilience.quota.acquire(identity.tenant_id)
            except QuotaExceededError:
                if self.telemetry:
                    self.telemetry.rejections.labels(reason="quota").inc()
                raise
        thread_id = scoped_thread_id(identity.tenant_id, command.conversation_id)
        capacity = self.resilience.concurrency.slot() if self.resilience else nullcontext()
        if self.telemetry:
            self.telemetry.in_flight.inc()
            self.telemetry.trace(
                "request_started",
                {
                    "request_id": command.request_id,
                    "tenant_hash": hash_identifier(identity.tenant_id),
                    "user_hash": hash_identifier(identity.user_id),
                    "conversation_hash": hash_identifier(command.conversation_id),
                },
            )
        try:
            if self.durable_recovery_enabled:
                with capacity:
                    response = self._query_durable(command, identity)
            else:
                with capacity, self.coordination.slot(thread_id):
                    record = self._claim(command, identity)
                    try:
                        state = self.runtime.graph.invoke(
                            self._inputs(command, identity, record),
                            config=self._config(command, record),
                        )
                    except Exception as exc:
                        raise ServiceExecutionError("RAG workflow execution failed") from exc
                    response = self._response(command, state)
                    self._remember(command, identity, response)
            if self.telemetry:
                elapsed = time.perf_counter() - started
                self.telemetry.observe_request(elapsed_seconds=elapsed, response=response)
                self.telemetry.trace(
                    "request_completed",
                    {
                        "request_id": command.request_id,
                        "tenant_hash": hash_identifier(identity.tenant_id),
                        "outcome": "refused" if response["refusal_reason"] else "success",
                        "reason": response["refusal_reason"] or "none",
                        "degraded": response["degraded"],
                        "elapsed_ms": round(elapsed * 1000, 3),
                        "step_count": response["usage"]["steps"],
                        "retrieval_attempts": response["usage"]["retrieval_attempts"],
                        "generation_attempts": response["usage"]["generation_attempts"],
                        "estimated_tokens": response["usage"]["estimated_tokens"],
                        "component_versions": response["component_versions"],
                        "citation_ids": [item["citation_id"] for item in response["citations"]],
                        "cited_chunk_ids": [item["chunk_id"] for item in response["citations"]],
                    },
                )
            return response
        except CapacityExceededError:
            if self.telemetry:
                self.telemetry.rejections.labels(reason="capacity").inc()
            raise
        except ConversationBusyError:
            if self.telemetry:
                self.telemetry.rejections.labels(reason="conversation_busy").inc()
                self.telemetry.observe_coordination(action="conversation_lock", outcome="busy")
            raise
        except CoordinationUnavailableError:
            if self.telemetry:
                self.telemetry.rejections.labels(reason="coordination_unavailable").inc()
                self.telemetry.observe_coordination(action="coordination", outcome="unavailable")
            raise
        finally:
            if self.telemetry:
                self.telemetry.in_flight.dec()

    def stream(self, command: QueryCommand, identity: IdentityClaims) -> Iterator[dict[str, Any]]:
        started = time.perf_counter()
        if self.resilience:
            try:
                self.resilience.quota.acquire(identity.tenant_id)
            except QuotaExceededError:
                if self.telemetry:
                    self.telemetry.rejections.labels(reason="quota").inc()
                raise
        thread_id = scoped_thread_id(identity.tenant_id, command.conversation_id)
        capacity = self.resilience.concurrency.slot() if self.resilience else nullcontext()
        if self.telemetry:
            self.telemetry.in_flight.inc()
        try:
            if self.durable_recovery_enabled:
                yield from self._stream_durable(command, identity, capacity)
                return
            with capacity, self.coordination.slot(thread_id):
                record = self._claim(command, identity)
                state: dict[str, Any] = self._inputs(command, identity, record)
                for update in self.runtime.graph.stream(state, config=self._config(command, record)):
                    for node, values in update.items():
                        state.update(values)
                        yield {
                            "type": "progress",
                            "request_id": command.request_id,
                            "node": node,
                        }
                response = self._response(command, state)
                self._remember(command, identity, response)
                if self.telemetry:
                    self.telemetry.observe_request(
                        elapsed_seconds=time.perf_counter() - started,
                        response=response,
                    )
                yield {"type": "answer", "data": response}
        except CapacityExceededError:
            if self.telemetry:
                self.telemetry.rejections.labels(reason="capacity").inc()
            raise
        except ConversationBusyError:
            if self.telemetry:
                self.telemetry.rejections.labels(reason="conversation_busy").inc()
                self.telemetry.observe_coordination(action="conversation_lock", outcome="busy")
            raise
        except CoordinationUnavailableError:
            if self.telemetry:
                self.telemetry.rejections.labels(reason="coordination_unavailable").inc()
                self.telemetry.observe_coordination(action="coordination", outcome="unavailable")
            raise
        finally:
            if self.telemetry:
                self.telemetry.in_flight.dec()

    def _stream_durable(
        self,
        command: QueryCommand,
        identity: IdentityClaims,
        capacity: Any,
    ) -> Iterator[dict[str, Any]]:
        record = self._claim(command, identity)
        run = self._submit_run(command, identity, record)
        if run.status == RunStatus.SUCCEEDED and run.result is not None:
            yield {"type": "answer", "data": run.result}
            return
        self._raise_for_terminal(run)
        claimed = self.runs.claim(
            identity.tenant_id,
            command.request_id,
            owner=self._owner_id,
            lease_seconds=self.runtime.settings.run_lease_seconds,
        )
        if claimed is None:
            current = self.runs.get(identity.tenant_id, command.request_id) or run
            self._raise_for_terminal(current)
            raise RequestPendingError(command.request_id, current.status)
        try:
            with capacity, self.coordination.slot(record.thread_id), RunLeaseHeartbeat(
                self.runs,
                claimed,
                lease_seconds=self.runtime.settings.run_lease_seconds,
                interval_seconds=self.runtime.settings.run_heartbeat_seconds,
            ) as heartbeat:
                config = self._config(command, record, claimed)
                snapshot = self._validated_snapshot(claimed, config)
                state: dict[str, Any] = dict(snapshot.values or {})
                graph_input: dict[str, Any] | None
                if not snapshot.values:
                    graph_input = self._inputs(command, identity, record)
                    state = dict(graph_input)
                elif snapshot.next:
                    self.runtime.graph.update_state(
                        config,
                        {
                            "deadline_at_ms": int(time.time() * 1000)
                            + int(self.runtime.settings.request_timeout_seconds * 1000)
                        },
                    )
                    graph_input = None
                else:
                    graph_input = None
                if not snapshot.values or snapshot.next:
                    for update in self.runtime.graph.stream(
                        graph_input,
                        config=config,
                        durability="sync",
                    ):
                        for node, values in update.items():
                            state.update(values)
                            yield {
                                "type": "progress",
                                "request_id": command.request_id,
                                "node": node,
                            }
                if heartbeat.lost:
                    raise RunLeaseLostError("run lease heartbeat was lost")
                response = self._response(command, state)
                self.runs.finalize(
                    claimed,
                    response=response,
                    question=command.question,
                    conversation_ttl_seconds=self.runtime.settings.conversation_ttl_seconds,
                    summary_max_chars=self.runtime.settings.conversation_summary_max_chars,
                )
                yield {"type": "answer", "data": response}
        except GeneratorExit:
            try:
                self.runs.mark_terminal(
                    claimed,
                    status=RunStatus.CANCELLED,
                    error_category="CLIENT_DISCONNECTED",
                )
            except RunLeaseLostError:
                pass
            raise
        except IncompatibleRunError:
            self.runs.mark_terminal(
                claimed,
                status=RunStatus.FAILED_TERMINAL,
                error_category="INCOMPATIBLE_GRAPH_VERSION",
            )
            raise RequestTerminalError(
                claimed.request_id,
                RunStatus.FAILED_TERMINAL,
                "INCOMPATIBLE_GRAPH_VERSION",
            )
        except RunLeaseLostError:
            raise RequestPendingError(claimed.request_id, RunStatus.RUNNING)
        except Exception:
            self._mark_retryable(claimed, "STREAM_EXECUTION_FAILED")
            raise

    def get_request(self, request_id: str, identity: IdentityClaims) -> RequestRun:
        if self.runs is None:
            raise KeyError("request status is unavailable in local mode")
        return self.runs.get_authorized(identity.tenant_id, request_id, identity.user_id)

    def get_conversation(self, conversation_id: str, identity: IdentityClaims) -> ConversationRecord:
        return self.runtime.conversations.get(
            conversation_id,
            tenant_id=identity.tenant_id,
            user_id=identity.user_id,
        )

    def delete_conversation(self, conversation_id: str, identity: IdentityClaims) -> bool:
        thread_id = scoped_thread_id(identity.tenant_id, conversation_id)
        with self.coordination.slot(thread_id):
            try:
                self.runtime.conversations.get(
                    conversation_id,
                    tenant_id=identity.tenant_id,
                    user_id=identity.user_id,
                )
            except KeyError:
                return False
            if self.runs is not None:
                self.runs.delete_checkpoint_threads(
                    identity.tenant_id,
                    conversation_id,
                    self.runtime.checkpoints.saver,
                )
            return self.runtime.conversations.delete(
                conversation_id,
                tenant_id=identity.tenant_id,
                user_id=identity.user_id,
                checkpointer=self.runtime.checkpoints.saver,
            )

    def ready(self) -> bool:
        return all(value == "ok" for value in self.ready_checks().values())

    def ready_checks(self) -> dict[str, str]:
        checks = {
            "checkpoint_store": "ok" if self.runtime.checkpoints.ping() else "failed",
            "conversation_store": "ok" if self.runtime.conversations.ping() else "failed",
            "coordination_store": "ok" if self.coordination.ping() else "failed",
        }
        if self.runs is not None:
            checks["request_run_store"] = "ok" if self.runs.ping() else "failed"
        if self.telemetry:
            for dependency, state in checks.items():
                self.telemetry.set_dependency_ready(dependency, state == "ok")
        return checks

    def metrics(self) -> bytes:
        if not self.telemetry:
            return b""
        if self.runs is not None:
            try:
                count, oldest = self.runs.backlog()
                self.telemetry.set_recovery_backlog(count=count, oldest_age_seconds=oldest)
            except Exception:
                pass
        return self.telemetry.metrics()


def make_command(
    *,
    question: str,
    conversation_id: str | None,
    request_id: str | None,
    constraints: Mapping[str, Any],
) -> QueryCommand:
    return QueryCommand(
        question=question.strip(),
        conversation_id=(conversation_id or str(uuid4())).strip(),
        request_id=(request_id or str(uuid4())).strip(),
        constraints=constraints,
    )
