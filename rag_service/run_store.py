from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping
from uuid import uuid4


class RunStatus(StrEnum):
    RECEIVED = "RECEIVED"
    RUNNING = "RUNNING"
    RETRYABLE = "RETRYABLE"
    SUCCEEDED = "SUCCEEDED"
    FAILED_TERMINAL = "FAILED_TERMINAL"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


ACTIVE_RUN_STATUSES = (RunStatus.RECEIVED, RunStatus.RUNNING, RunStatus.RETRYABLE)
TERMINAL_RUN_STATUSES = (
    RunStatus.SUCCEEDED,
    RunStatus.FAILED_TERMINAL,
    RunStatus.CANCELLED,
    RunStatus.EXPIRED,
)


class RunStoreError(RuntimeError):
    """Base class for durable run lifecycle errors."""


class IdempotencyConflictError(RunStoreError):
    """The same tenant/request key was reused with a different payload."""


class ActiveConversationRunError(RunStoreError):
    """A newer turn attempted to overtake unfinished work in one conversation."""

    def __init__(self, request_id: str):
        super().__init__("conversation has an unfinished request")
        self.request_id = request_id


class RunLeaseLostError(RunStoreError):
    """The caller no longer owns the run's fencing token."""


class RunAccessError(PermissionError):
    """A request result was requested by a different user."""


class RunNotFoundError(KeyError):
    """A tenant-scoped request run does not exist."""


@dataclass(frozen=True)
class RequestRun:
    tenant_id: str
    request_id: str
    conversation_id: str
    user_id: str
    thread_id: str
    input_hash: str
    request_payload: dict[str, Any]
    status: RunStatus
    graph_version: str
    input_schema_version: int
    attempt_count: int
    max_attempts: int
    lease_owner: str | None
    lease_token: str | None
    lease_until_ms: int | None
    heartbeat_at_ms: int | None
    submitted_at_ms: int
    started_at_ms: int | None
    updated_at_ms: int
    completed_at_ms: int | None
    recovery_expires_at_ms: int
    next_retry_at_ms: int
    result: dict[str, Any] | None
    error_category: str | None


def canonical_payload_hash(
    *,
    tenant_id: str,
    user_id: str,
    conversation_id: str,
    question: str,
    constraints: Mapping[str, Any],
) -> str:
    payload = {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "conversation_id": conversation_id,
        "question": question,
        "constraints": dict(constraints),
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def scoped_run_thread_id(tenant_id: str, conversation_id: str, request_id: str) -> str:
    payload = f"{tenant_id}\0{conversation_id}\0{request_id}".encode("utf-8")
    return f"rag-run-{hashlib.sha256(payload).hexdigest()}"


def _now_ms() -> int:
    return int(time.time() * 1000)


class PostgresRequestRunStore:
    """PostgreSQL request ledger, durable queue, and fenced finalization boundary."""

    def __init__(self, pool: Any):
        self._pool = pool

    @staticmethod
    def setup(pool: Any) -> None:
        with pool.connection() as connection, connection.transaction():
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS rag_request_runs (
                    tenant_id TEXT NOT NULL,
                    request_id VARCHAR(128) NOT NULL,
                    conversation_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    thread_id VARCHAR(255) NOT NULL UNIQUE,
                    input_hash CHAR(64) NOT NULL,
                    request_payload JSONB NOT NULL,
                    status TEXT NOT NULL CHECK (status IN (
                        'RECEIVED', 'RUNNING', 'RETRYABLE', 'SUCCEEDED',
                        'FAILED_TERMINAL', 'CANCELLED', 'EXPIRED'
                    )),
                    graph_version TEXT NOT NULL,
                    input_schema_version INTEGER NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
                    max_attempts INTEGER NOT NULL CHECK (max_attempts > 0),
                    lease_owner TEXT,
                    lease_token UUID,
                    lease_until_ms BIGINT,
                    heartbeat_at_ms BIGINT,
                    submitted_at_ms BIGINT NOT NULL,
                    started_at_ms BIGINT,
                    updated_at_ms BIGINT NOT NULL,
                    completed_at_ms BIGINT,
                    recovery_expires_at_ms BIGINT NOT NULL,
                    next_retry_at_ms BIGINT NOT NULL,
                    result_json JSONB,
                    error_category TEXT,
                    PRIMARY KEY (tenant_id, request_id),
                    FOREIGN KEY (tenant_id, conversation_id)
                        REFERENCES rag_conversations(tenant_id, conversation_id)
                        ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uq_rag_request_runs_active_conversation
                ON rag_request_runs(tenant_id, conversation_id)
                WHERE status IN ('RECEIVED', 'RUNNING', 'RETRYABLE')
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_rag_request_runs_recovery
                ON rag_request_runs(next_retry_at_ms, lease_until_ms, submitted_at_ms)
                WHERE status IN ('RECEIVED', 'RUNNING', 'RETRYABLE')
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_rag_request_runs_conversation
                ON rag_request_runs(tenant_id, conversation_id, submitted_at_ms)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS rag_conversation_turns (
                    tenant_id TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    request_id VARCHAR(128) NOT NULL,
                    user_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    created_at_ms BIGINT NOT NULL,
                    PRIMARY KEY (tenant_id, conversation_id, request_id),
                    FOREIGN KEY (tenant_id, conversation_id)
                        REFERENCES rag_conversations(tenant_id, conversation_id)
                        ON DELETE CASCADE
                )
                """
            )

    @staticmethod
    def _row(row: Mapping[str, Any] | None) -> RequestRun | None:
        if row is None:
            return None
        data = dict(row)
        data["status"] = RunStatus(data["status"])
        data["request_payload"] = dict(data.pop("request_payload") or {})
        result = data.pop("result_json")
        data["result"] = dict(result) if result is not None else None
        if data.get("lease_token") is not None:
            data["lease_token"] = str(data["lease_token"])
        return RequestRun(**data)

    def submit(
        self,
        *,
        tenant_id: str,
        request_id: str,
        conversation_id: str,
        user_id: str,
        question: str,
        constraints: Mapping[str, Any],
        graph_version: str,
        input_schema_version: int,
        max_attempts: int,
        recovery_window_seconds: int,
        initial_recovery_delay_seconds: float = 0.0,
        now_ms: int | None = None,
    ) -> tuple[RequestRun, bool]:
        from psycopg import errors
        from psycopg.types.json import Jsonb

        current_ms = _now_ms() if now_ms is None else now_ms
        payload = {"question": question, "constraints": dict(constraints)}
        fingerprint = canonical_payload_hash(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            question=question,
            constraints=constraints,
        )
        thread_id = scoped_run_thread_id(tenant_id, conversation_id, request_id)
        try:
            with self._pool.connection() as connection, connection.transaction():
                row = connection.execute(
                    """
                    INSERT INTO rag_request_runs (
                        tenant_id, request_id, conversation_id, user_id, thread_id,
                        input_hash, request_payload, status, graph_version,
                        input_schema_version, max_attempts, submitted_at_ms, updated_at_ms,
                        recovery_expires_at_ms, next_retry_at_ms
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, 'RECEIVED', %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (tenant_id, request_id) DO NOTHING
                    RETURNING *
                    """,
                    (
                        tenant_id,
                        request_id,
                        conversation_id,
                        user_id,
                        thread_id,
                        fingerprint,
                        Jsonb(payload),
                        graph_version,
                        input_schema_version,
                        max_attempts,
                        current_ms,
                        current_ms,
                        current_ms + recovery_window_seconds * 1000,
                        current_ms + int(initial_recovery_delay_seconds * 1000),
                    ),
                ).fetchone()
        except errors.UniqueViolation as exc:
            if exc.diag.constraint_name == "uq_rag_request_runs_active_conversation":
                existing = self.find_active_for_conversation(tenant_id, conversation_id)
                raise ActiveConversationRunError(existing.request_id if existing else "") from exc
            raise
        created = row is not None
        run = self._row(row) if created else self.get(tenant_id, request_id)
        if run is None:
            raise RunStoreError("request run disappeared after submission")
        if (
            run.input_hash != fingerprint
            or run.user_id != user_id
            or run.conversation_id != conversation_id
        ):
            raise IdempotencyConflictError("request id was already used with a different payload")
        return run, created

    def get(self, tenant_id: str, request_id: str) -> RequestRun | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                "SELECT * FROM rag_request_runs WHERE tenant_id = %s AND request_id = %s",
                (tenant_id, request_id),
            ).fetchone()
        return self._row(row)

    def get_authorized(self, tenant_id: str, request_id: str, user_id: str) -> RequestRun:
        run = self.get(tenant_id, request_id)
        if run is None:
            raise RunNotFoundError("request does not exist")
        if run.user_id != user_id:
            raise RunAccessError("request belongs to a different user")
        return run

    def find_active_for_conversation(self, tenant_id: str, conversation_id: str) -> RequestRun | None:
        with self._pool.connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM rag_request_runs
                WHERE tenant_id = %s AND conversation_id = %s
                  AND status IN ('RECEIVED', 'RUNNING', 'RETRYABLE')
                ORDER BY submitted_at_ms
                LIMIT 1
                """,
                (tenant_id, conversation_id),
            ).fetchone()
        return self._row(row)

    def claim(
        self,
        tenant_id: str,
        request_id: str,
        *,
        owner: str,
        lease_seconds: float,
        now_ms: int | None = None,
    ) -> RequestRun | None:
        current_ms = _now_ms() if now_ms is None else now_ms
        token = str(uuid4())
        with self._pool.connection() as connection, connection.transaction():
            row = connection.execute(
                """
                UPDATE rag_request_runs
                SET status = 'RUNNING',
                    attempt_count = attempt_count + 1,
                    lease_owner = %s,
                    lease_token = %s,
                    lease_until_ms = %s,
                    heartbeat_at_ms = %s,
                    started_at_ms = COALESCE(started_at_ms, %s),
                    updated_at_ms = %s,
                    error_category = NULL
                WHERE tenant_id = %s AND request_id = %s
                  AND status IN ('RECEIVED', 'RUNNING', 'RETRYABLE')
                  AND (status <> 'RUNNING' OR lease_until_ms IS NULL OR lease_until_ms <= %s)
                  AND (status = 'RECEIVED' OR next_retry_at_ms <= %s)
                  AND recovery_expires_at_ms > %s
                  AND attempt_count < max_attempts
                RETURNING *
                """,
                (
                    owner,
                    token,
                    current_ms + int(lease_seconds * 1000),
                    current_ms,
                    current_ms,
                    current_ms,
                    tenant_id,
                    request_id,
                    current_ms,
                    current_ms,
                    current_ms,
                ),
            ).fetchone()
        return self._row(row)

    def claim_next(self, *, owner: str, lease_seconds: float, now_ms: int | None = None) -> RequestRun | None:
        current_ms = _now_ms() if now_ms is None else now_ms
        token = str(uuid4())
        with self._pool.connection() as connection, connection.transaction():
            row = connection.execute(
                """
                WITH candidate AS (
                    SELECT tenant_id, request_id
                    FROM rag_request_runs
                    WHERE status IN ('RECEIVED', 'RUNNING', 'RETRYABLE')
                      AND (status <> 'RUNNING' OR lease_until_ms IS NULL OR lease_until_ms <= %s)
                      AND next_retry_at_ms <= %s
                      AND recovery_expires_at_ms > %s
                      AND attempt_count < max_attempts
                    ORDER BY next_retry_at_ms, submitted_at_ms
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE rag_request_runs AS run
                SET status = 'RUNNING',
                    attempt_count = run.attempt_count + 1,
                    lease_owner = %s,
                    lease_token = %s,
                    lease_until_ms = %s,
                    heartbeat_at_ms = %s,
                    started_at_ms = COALESCE(run.started_at_ms, %s),
                    updated_at_ms = %s,
                    error_category = NULL
                FROM candidate
                WHERE run.tenant_id = candidate.tenant_id
                  AND run.request_id = candidate.request_id
                RETURNING run.*
                """,
                (
                    current_ms,
                    current_ms,
                    current_ms,
                    owner,
                    token,
                    current_ms + int(lease_seconds * 1000),
                    current_ms,
                    current_ms,
                    current_ms,
                ),
            ).fetchone()
        return self._row(row)

    def heartbeat(self, run: RequestRun, *, lease_seconds: float, now_ms: int | None = None) -> bool:
        if not run.lease_token:
            return False
        current_ms = _now_ms() if now_ms is None else now_ms
        with self._pool.connection() as connection, connection.transaction():
            result = connection.execute(
                """
                UPDATE rag_request_runs
                SET lease_until_ms = %s, heartbeat_at_ms = %s, updated_at_ms = %s
                WHERE tenant_id = %s AND request_id = %s
                  AND status = 'RUNNING' AND lease_token = %s
                """,
                (
                    current_ms + int(lease_seconds * 1000),
                    current_ms,
                    current_ms,
                    run.tenant_id,
                    run.request_id,
                    run.lease_token,
                ),
            )
        return bool(result.rowcount)

    def mark_retryable(
        self,
        run: RequestRun,
        *,
        error_category: str,
        retry_delay_seconds: float,
        now_ms: int | None = None,
    ) -> RequestRun:
        current_ms = _now_ms() if now_ms is None else now_ms
        expired = current_ms >= run.recovery_expires_at_ms
        attempts_exhausted = run.attempt_count >= run.max_attempts
        exhausted = attempts_exhausted or expired
        status = RunStatus.EXPIRED if expired else RunStatus.FAILED_TERMINAL
        if not exhausted:
            status = RunStatus.RETRYABLE
        elif expired:
            error_category = "RECOVERY_EXPIRED"
        else:
            error_category = "MAX_ATTEMPTS_EXCEEDED"
        completed_at = current_ms if status in TERMINAL_RUN_STATUSES else None
        with self._pool.connection() as connection, connection.transaction():
            row = connection.execute(
                """
                UPDATE rag_request_runs
                SET status = %s, error_category = %s, next_retry_at_ms = %s,
                    lease_owner = NULL, lease_token = NULL, lease_until_ms = NULL,
                    heartbeat_at_ms = NULL, completed_at_ms = %s, updated_at_ms = %s
                WHERE tenant_id = %s AND request_id = %s
                  AND status = 'RUNNING' AND lease_token = %s
                RETURNING *
                """,
                (
                    status.value,
                    error_category,
                    current_ms + int(retry_delay_seconds * 1000),
                    completed_at,
                    current_ms,
                    run.tenant_id,
                    run.request_id,
                    run.lease_token,
                ),
            ).fetchone()
        updated = self._row(row)
        if updated is None:
            raise RunLeaseLostError("run lease was lost before retry transition")
        return updated

    def mark_terminal(
        self,
        run: RequestRun,
        *,
        status: RunStatus,
        error_category: str,
        now_ms: int | None = None,
    ) -> RequestRun:
        if status not in {RunStatus.FAILED_TERMINAL, RunStatus.CANCELLED, RunStatus.EXPIRED}:
            raise ValueError("status must be a non-success terminal state")
        current_ms = _now_ms() if now_ms is None else now_ms
        with self._pool.connection() as connection, connection.transaction():
            row = connection.execute(
                """
                UPDATE rag_request_runs
                SET status = %s, error_category = %s, completed_at_ms = %s, updated_at_ms = %s,
                    lease_owner = NULL, lease_token = NULL, lease_until_ms = NULL, heartbeat_at_ms = NULL
                WHERE tenant_id = %s AND request_id = %s
                  AND status = 'RUNNING' AND lease_token = %s
                RETURNING *
                """,
                (
                    status.value,
                    error_category,
                    current_ms,
                    current_ms,
                    run.tenant_id,
                    run.request_id,
                    run.lease_token,
                ),
            ).fetchone()
        updated = self._row(row)
        if updated is None:
            raise RunLeaseLostError("run lease was lost before terminal transition")
        return updated

    def finalize(
        self,
        run: RequestRun,
        *,
        response: Mapping[str, Any],
        question: str,
        conversation_ttl_seconds: int,
        summary_max_chars: int,
        now_ms: int | None = None,
    ) -> RequestRun:
        from psycopg.types.json import Jsonb

        if not run.lease_token:
            raise RunLeaseLostError("run has no fencing token")
        current_ms = _now_ms() if now_ms is None else now_ms
        expires_at_ms = current_ms + conversation_ttl_seconds * 1000
        answer = str(response.get("answer", ""))
        turn = f"User: {question.strip()}\nAssistant: {answer.strip()}".strip()
        with self._pool.connection() as connection, connection.transaction():
            owned = connection.execute(
                """
                SELECT 1 FROM rag_request_runs
                WHERE tenant_id = %s AND request_id = %s
                  AND status = 'RUNNING' AND lease_token = %s
                FOR UPDATE
                """,
                (run.tenant_id, run.request_id, run.lease_token),
            ).fetchone()
            if owned is None:
                raise RunLeaseLostError("run lease was lost before finalization")
            inserted = connection.execute(
                """
                INSERT INTO rag_conversation_turns
                    (tenant_id, conversation_id, request_id, user_id, question, answer, created_at_ms)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id, conversation_id, request_id) DO NOTHING
                RETURNING request_id
                """,
                (
                    run.tenant_id,
                    run.conversation_id,
                    run.request_id,
                    run.user_id,
                    question,
                    answer,
                    current_ms,
                ),
            ).fetchone()
            if inserted is not None:
                updated_conversation = connection.execute(
                    """
                    UPDATE rag_conversations
                    SET summary = RIGHT(CASE WHEN summary = '' THEN %s ELSE summary || E'\n' || %s END, %s),
                        updated_at_ms = %s, expires_at_ms = %s
                    WHERE tenant_id = %s AND conversation_id = %s AND user_id = %s
                    RETURNING conversation_id
                    """,
                    (
                        turn,
                        turn,
                        summary_max_chars,
                        current_ms,
                        expires_at_ms,
                        run.tenant_id,
                        run.conversation_id,
                        run.user_id,
                    ),
                ).fetchone()
                if updated_conversation is None:
                    raise RunAccessError("conversation ownership changed before finalization")
            row = connection.execute(
                """
                UPDATE rag_request_runs
                SET status = 'SUCCEEDED', result_json = %s, error_category = NULL,
                    completed_at_ms = %s, updated_at_ms = %s,
                    lease_owner = NULL, lease_token = NULL, lease_until_ms = NULL, heartbeat_at_ms = NULL
                WHERE tenant_id = %s AND request_id = %s
                  AND status = 'RUNNING' AND lease_token = %s
                RETURNING *
                """,
                (
                    Jsonb(dict(response)),
                    current_ms,
                    current_ms,
                    run.tenant_id,
                    run.request_id,
                    run.lease_token,
                ),
            ).fetchone()
        finalized = self._row(row)
        if finalized is None:
            raise RunLeaseLostError("run lease was lost during finalization")
        return finalized

    def reconcile_expired(self, *, now_ms: int | None = None) -> int:
        current_ms = _now_ms() if now_ms is None else now_ms
        with self._pool.connection() as connection, connection.transaction():
            result = connection.execute(
                """
                UPDATE rag_request_runs
                SET status = CASE
                        WHEN recovery_expires_at_ms <= %s THEN 'EXPIRED'
                        ELSE 'FAILED_TERMINAL'
                    END,
                    error_category = CASE
                        WHEN recovery_expires_at_ms <= %s THEN 'RECOVERY_EXPIRED'
                        ELSE 'MAX_ATTEMPTS_EXCEEDED'
                    END,
                    completed_at_ms = %s, updated_at_ms = %s,
                    lease_owner = NULL, lease_token = NULL, lease_until_ms = NULL, heartbeat_at_ms = NULL
                WHERE status IN ('RECEIVED', 'RUNNING', 'RETRYABLE')
                  AND (recovery_expires_at_ms <= %s OR attempt_count >= max_attempts)
                  AND (status <> 'RUNNING' OR lease_until_ms IS NULL OR lease_until_ms <= %s)
                """,
                (current_ms, current_ms, current_ms, current_ms, current_ms, current_ms),
            )
        return int(result.rowcount or 0)

    def delete_checkpoint_threads(self, tenant_id: str, conversation_id: str, checkpointer: Any) -> int:
        with self._pool.connection() as connection:
            rows = connection.execute(
                "SELECT thread_id FROM rag_request_runs WHERE tenant_id = %s AND conversation_id = %s",
                (tenant_id, conversation_id),
            ).fetchall()
        for row in rows:
            checkpointer.delete_thread(str(row["thread_id"]))
        return len(rows)

    def ping(self) -> bool:
        try:
            with self._pool.connection() as connection:
                row = connection.execute(
                    "SELECT to_regclass('public.rag_request_runs') AS table_name"
                ).fetchone()
                return bool(row and row["table_name"])
        except Exception:
            return False

    def backlog(self, *, now_ms: int | None = None) -> tuple[int, float]:
        current_ms = _now_ms() if now_ms is None else now_ms
        with self._pool.connection() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count, MIN(submitted_at_ms) AS oldest
                FROM rag_request_runs
                WHERE status IN ('RECEIVED', 'RETRYABLE')
                   OR (status = 'RUNNING' AND (lease_until_ms IS NULL OR lease_until_ms <= %s))
                """,
                (current_ms,),
            ).fetchone()
        count = int(row["count"] or 0)
        oldest = int(row["oldest"] or current_ms)
        return count, max(0.0, (current_ms - oldest) / 1000.0) if count else 0.0


class RunLeaseHeartbeat:
    """Renew a run lease while graph execution blocks in model or retrieval calls."""

    def __init__(self, store: PostgresRequestRunStore, run: RequestRun, *, lease_seconds: float, interval_seconds: float):
        self._store = store
        self._run = run
        self._lease_seconds = lease_seconds
        self._interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._lost = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def lost(self) -> bool:
        return self._lost.is_set()

    def __enter__(self) -> "RunLeaseHeartbeat":
        self._thread = threading.Thread(
            target=self._renew,
            name=f"rag-run-heartbeat-{self._run.request_id[:16]}",
            daemon=True,
        )
        self._thread.start()
        return self

    def _renew(self) -> None:
        while not self._stop.wait(self._interval_seconds):
            try:
                if not self._store.heartbeat(self._run, lease_seconds=self._lease_seconds):
                    self._lost.set()
                    return
            except Exception:
                self._lost.set()
                return

    def __exit__(self, exc_type, exc, traceback) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=min(self._interval_seconds, 1.0))


def create_request_run_store(settings: Any, checkpoint_handle: Any) -> PostgresRequestRunStore | None:
    if settings.state_backend != "postgres":
        return None
    return PostgresRequestRunStore(checkpoint_handle.resource)
