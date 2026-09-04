from __future__ import annotations

import threading
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from rag_service.application import ApplicationRuntime
from rag_service.auth import IdentityClaims
from rag_service.conversation import ConversationRecord, scoped_thread_id
from rag_service.resilience import CapacityExceededError, QuotaExceededError
from rag_service.telemetry import hash_identifier


class ServiceExecutionError(RuntimeError):
    """Raised when an internal dependency prevents request completion."""


@dataclass(frozen=True)
class QueryCommand:
    question: str
    conversation_id: str
    request_id: str
    constraints: Mapping[str, Any]


@dataclass
class _LockEntry:
    lock: threading.Lock
    references: int = 0


class RAGService:
    def __init__(self, runtime: ApplicationRuntime):
        self.runtime = runtime
        self.resilience = getattr(runtime, "resilience", None)
        self.telemetry = getattr(runtime, "telemetry", None)
        self._locks: dict[str, _LockEntry] = {}
        self._locks_guard = threading.Lock()

    @contextmanager
    def _conversation_slot(self, thread_id: str):
        with self._locks_guard:
            entry = self._locks.setdefault(thread_id, _LockEntry(threading.Lock()))
            entry.references += 1
        try:
            with entry.lock:
                yield
        finally:
            with self._locks_guard:
                entry.references -= 1
                if entry.references == 0:
                    self._locks.pop(thread_id, None)

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

    def _config(self, command: QueryCommand, record: ConversationRecord) -> dict[str, Any]:
        return {
            "configurable": {"thread_id": record.thread_id},
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
            with capacity, self._conversation_slot(thread_id):
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
            with capacity, self._conversation_slot(thread_id):
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
        finally:
            if self.telemetry:
                self.telemetry.in_flight.dec()

    def get_conversation(self, conversation_id: str, identity: IdentityClaims) -> ConversationRecord:
        return self.runtime.conversations.get(
            conversation_id,
            tenant_id=identity.tenant_id,
            user_id=identity.user_id,
        )

    def delete_conversation(self, conversation_id: str, identity: IdentityClaims) -> bool:
        thread_id = scoped_thread_id(identity.tenant_id, conversation_id)
        with self._conversation_slot(thread_id):
            return self.runtime.conversations.delete(
                conversation_id,
                tenant_id=identity.tenant_id,
                user_id=identity.user_id,
                checkpointer=self.runtime.checkpoints.saver,
            )

    def ready(self) -> bool:
        return self.runtime.conversations.ping()

    def metrics(self) -> bytes:
        if not self.telemetry:
            return b""
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
