import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from psycopg import connect
from psycopg.rows import dict_row
from redis import Redis

from rag_service.checkpointing import create_checkpointer, create_sqlite_checkpointer
from rag_service.conversation import ConversationStore, PostgresConversationStore, scoped_thread_id
from rag_service.coordination import ConversationBusyError, LocalConversationCoordinator, create_coordination
from rag_service.auth import IdentityClaims
from rag_service.migrations import (
    inspect_sqlite_state,
    migrate_postgres_state,
    migrate_sqlite_to_postgres,
    prune_expired_state,
)
from rag_service.resilience import QuotaExceededError
from rag_service.run_store import (
    ActiveConversationRunError,
    IdempotencyConflictError,
    PostgresRequestRunStore,
    RunLeaseLostError,
    RunStatus,
)
from rag_service.settings import Settings
from rag_service.service import RAGService, ServiceExecutionError, make_command


RUN_INTEGRATION = os.getenv("RAG_RUN_INTEGRATION") == "1"
DATABASE_URL = os.getenv(
    "RAG_TEST_DATABASE_URL",
    "postgresql://rag_test:rag_test_only@127.0.0.1:55432/rag_test",
)
REDIS_URL = os.getenv("RAG_TEST_REDIS_URL", "redis://127.0.0.1:56379/0")


class TinyState(TypedDict):
    value: str


class RecoveryState(TypedDict, total=False):
    request_context: dict
    question: str
    conversation_summary: str
    query_constraints: dict
    completed: list[str]
    answer_result: dict
    component_versions: dict[str, str]


def build_tiny_graph(checkpointer):
    builder = StateGraph(TinyState)
    builder.add_node("finish", lambda state: {"value": state["value"]})
    builder.add_edge(START, "finish")
    builder.add_edge("finish", END)
    return builder.compile(checkpointer=checkpointer)


def build_recovery_graph(checkpointer, *, fail_second: bool):
    builder = StateGraph(RecoveryState)
    builder.add_node("first", lambda state: {"completed": ["first"]})

    def second(state):
        if fail_second:
            raise RuntimeError("injected process failure")
        return {
            "completed": [*state.get("completed", []), "second"],
            "answer_result": {"answer": "recovered", "citations": []},
            "component_versions": {"graph": "graph2-bounded-v1"},
        }

    builder.add_node("second", second)
    builder.add_edge(START, "first")
    builder.add_edge("first", "second")
    builder.add_edge("second", END)
    return builder.compile(checkpointer=checkpointer)


class RecoveryResolver:
    def resolve(self, **kwargs):
        return IdentityClaims("tenant-a", "alice", ("group:sales",), "policy-v2")


@unittest.skipUnless(RUN_INTEGRATION, "set RAG_RUN_INTEGRATION=1 and start the integration Compose profile")
class DistributedStateIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not DATABASE_URL.endswith("/rag_test"):
            raise RuntimeError("integration tests refuse to modify a database not named rag_test")
        cls.settings = Settings(
            state_backend="postgres",
            database_url=DATABASE_URL,
            redis_url=REDIS_URL,
            db_pool_min_size=1,
            db_pool_max_size=4,
            db_pool_timeout_seconds=5,
            conversation_lock_ttl_seconds=2,
            conversation_lock_acquire_timeout_seconds=0.05,
            tenant_request_burst=1,
            tenant_requests_per_minute=1,
        )
        migrate_postgres_state(cls.settings)

    def setUp(self):
        with connect(DATABASE_URL, autocommit=True, row_factory=dict_row) as connection:
            connection.execute(
                "TRUNCATE checkpoint_writes, checkpoint_blobs, checkpoints, "
                "rag_conversation_turns, rag_request_runs, rag_conversations"
            )
        Redis.from_url(REDIS_URL).flushdb()

    def test_two_independent_pools_share_checkpoint_and_conversation_state(self):
        first = create_checkpointer(self.settings)
        second = create_checkpointer(self.settings)
        try:
            first_graph = build_tiny_graph(first.saver)
            config = {"configurable": {"thread_id": "shared-thread"}}
            first_graph.invoke({"value": "persisted"}, config=config)
            first_store = PostgresConversationStore(first.resource)
            first_store.claim(
                "conversation-1",
                tenant_id="tenant-a",
                user_id="alice",
                ttl_seconds=60,
            )

            restored = build_tiny_graph(second.saver).get_state(config)
            second_store = PostgresConversationStore(second.resource)
            conversation = second_store.get(
                "conversation-1",
                tenant_id="tenant-a",
                user_id="alice",
            )

            self.assertEqual(restored.values["value"], "persisted")
            self.assertEqual(conversation.user_id, "alice")
        finally:
            first.close()
            second.close()

    def test_redis_lock_and_quota_are_shared_across_clients(self):
        first_coordinator, first_quota = create_coordination(self.settings)
        second_coordinator, second_quota = create_coordination(self.settings)
        try:
            first_quota.acquire("tenant-a")
            with self.assertRaises(QuotaExceededError):
                second_quota.acquire("tenant-a")
            with first_coordinator.slot("thread-1"):
                with self.assertRaises(ConversationBusyError):
                    with second_coordinator.slot("thread-1"):
                        pass
            with second_coordinator.slot("thread-1"):
                pass
        finally:
            first_coordinator.close()
            second_coordinator.close()

    def test_sqlite_state_migrates_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            sqlite_path = str(Path(directory) / "legacy.sqlite3")
            source = create_sqlite_checkpointer(sqlite_path)
            source_store = ConversationStore(sqlite_path)
            try:
                config = {"configurable": {"thread_id": "migrated-thread"}}
                build_tiny_graph(source.saver).invoke({"value": "legacy"}, config=config)
                source_store.claim(
                    "legacy-conversation",
                    tenant_id="tenant-a",
                    user_id="alice",
                    ttl_seconds=60,
                )
            finally:
                source_store.close()
                source.close()

            source_digest = hashlib.sha256(Path(sqlite_path).read_bytes()).hexdigest()
            inventory = inspect_sqlite_state(sqlite_path)
            self.assertEqual(inventory["mode"], "dry-run")
            self.assertEqual(hashlib.sha256(Path(sqlite_path).read_bytes()).hexdigest(), source_digest)

            first = migrate_sqlite_to_postgres(sqlite_path, self.settings)
            second = migrate_sqlite_to_postgres(sqlite_path, self.settings)

            self.assertEqual(first["status"], "complete")
            self.assertEqual(second["status"], "complete")
            target = create_checkpointer(self.settings)
            try:
                restored = build_tiny_graph(target.saver).get_state(
                    {"configurable": {"thread_id": "migrated-thread"}}
                )
                self.assertEqual(restored.values["value"], "legacy")
            finally:
                target.close()

    def test_expired_postgres_state_is_pruned_under_redis_maintenance_lock(self):
        checkpoints = create_checkpointer(self.settings)
        try:
            conversation_id = "expired-conversation"
            thread_id = scoped_thread_id("tenant-a", conversation_id)
            config = {"configurable": {"thread_id": thread_id}}
            build_tiny_graph(checkpoints.saver).invoke({"value": "expired"}, config=config)
            PostgresConversationStore(checkpoints.resource).claim(
                conversation_id,
                tenant_id="tenant-a",
                user_id="alice",
                ttl_seconds=1,
                now_ms=0,
            )
        finally:
            checkpoints.close()

        result = prune_expired_state(self.settings)

        self.assertEqual(result, {"status": "complete", "deleted_conversations": 1})
        verification = create_checkpointer(self.settings)
        try:
            restored = build_tiny_graph(verification.saver).get_state(
                {"configurable": {"thread_id": thread_id}}
            )
            self.assertFalse(restored.values)
            with self.assertRaises(KeyError):
                PostgresConversationStore(verification.resource).get(
                    conversation_id,
                    tenant_id="tenant-a",
                    user_id="alice",
                )
        finally:
            verification.close()

    def test_failed_sqlite_migration_is_audited_without_error_details(self):
        with tempfile.TemporaryDirectory() as directory:
            sqlite_path = str(Path(directory) / "conflicting.sqlite3")
            source = create_sqlite_checkpointer(sqlite_path)
            source_store = ConversationStore(sqlite_path)
            try:
                source_store.claim(
                    "conflict",
                    tenant_id="tenant-a",
                    user_id="alice",
                    ttl_seconds=60,
                )
            finally:
                source_store.close()
                source.close()

            target = create_checkpointer(self.settings)
            try:
                PostgresConversationStore(target.resource).claim(
                    "conflict",
                    tenant_id="tenant-a",
                    user_id="bob",
                    ttl_seconds=60,
                )
            finally:
                target.close()

            with self.assertRaisesRegex(RuntimeError, "ownership conflicts"):
                migrate_sqlite_to_postgres(sqlite_path, self.settings)

            with connect(DATABASE_URL, row_factory=dict_row) as connection:
                audit = connection.execute(
                    "SELECT status, details FROM rag_state_migration_runs "
                    "WHERE status = 'failed' ORDER BY completed_at DESC LIMIT 1"
                ).fetchone()
            self.assertEqual(audit["status"], "failed")
            self.assertEqual(audit["details"]["error_type"], "RuntimeError")
            self.assertNotIn("message", audit["details"])

    def test_run_ledger_enforces_idempotency_and_conversation_order(self):
        checkpoints = create_checkpointer(self.settings)
        try:
            conversations = PostgresConversationStore(checkpoints.resource)
            conversations.claim(
                "conversation-ledger",
                tenant_id="tenant-a",
                user_id="alice",
                ttl_seconds=60,
            )
            runs = PostgresRequestRunStore(checkpoints.resource)
            first, created = runs.submit(
                tenant_id="tenant-a",
                request_id="request-1",
                conversation_id="conversation-ledger",
                user_id="alice",
                question="first question",
                constraints={"source_ids": ["source-1"]},
                graph_version="graph2-bounded-v1",
                input_schema_version=1,
                max_attempts=3,
                recovery_window_seconds=60,
                now_ms=1000,
            )
            duplicate, duplicate_created = runs.submit(
                tenant_id="tenant-a",
                request_id="request-1",
                conversation_id="conversation-ledger",
                user_id="alice",
                question="first question",
                constraints={"source_ids": ["source-1"]},
                graph_version="graph2-bounded-v1",
                input_schema_version=1,
                max_attempts=3,
                recovery_window_seconds=60,
                now_ms=1001,
            )

            self.assertTrue(created)
            self.assertFalse(duplicate_created)
            self.assertEqual(first.thread_id, duplicate.thread_id)
            with self.assertRaises(IdempotencyConflictError):
                runs.submit(
                    tenant_id="tenant-a",
                    request_id="request-1",
                    conversation_id="conversation-ledger",
                    user_id="alice",
                    question="changed question",
                    constraints={},
                    graph_version="graph2-bounded-v1",
                    input_schema_version=1,
                    max_attempts=3,
                    recovery_window_seconds=60,
                    now_ms=1002,
                )
            with self.assertRaises(ActiveConversationRunError):
                runs.submit(
                    tenant_id="tenant-a",
                    request_id="request-2",
                    conversation_id="conversation-ledger",
                    user_id="alice",
                    question="newer question",
                    constraints={},
                    graph_version="graph2-bounded-v1",
                    input_schema_version=1,
                    max_attempts=3,
                    recovery_window_seconds=60,
                    now_ms=1003,
                )
        finally:
            checkpoints.close()

    def test_fresh_received_run_is_reserved_for_the_api_fast_path(self):
        checkpoints = create_checkpointer(self.settings)
        try:
            PostgresConversationStore(checkpoints.resource).claim(
                "conversation-fast-path",
                tenant_id="tenant-a",
                user_id="alice",
                ttl_seconds=60,
                now_ms=1000,
            )
            runs = PostgresRequestRunStore(checkpoints.resource)
            submitted, _ = runs.submit(
                tenant_id="tenant-a",
                request_id="request-fast-path",
                conversation_id="conversation-fast-path",
                user_id="alice",
                question="question",
                constraints={},
                graph_version="graph2-bounded-v1",
                input_schema_version=1,
                max_attempts=3,
                recovery_window_seconds=60,
                initial_recovery_delay_seconds=10,
                now_ms=1000,
            )

            self.assertIsNone(
                runs.claim_next(owner="worker", lease_seconds=10, now_ms=1000)
            )
            api_claim = runs.claim(
                submitted.tenant_id,
                submitted.request_id,
                owner="api",
                lease_seconds=10,
                now_ms=1000,
            )

            self.assertIsNotNone(api_claim)
            self.assertEqual(api_claim.lease_owner, "api")
        finally:
            checkpoints.close()

    def test_lease_takeover_fences_old_owner_and_finalizes_one_turn(self):
        checkpoints = create_checkpointer(self.settings)
        try:
            conversations = PostgresConversationStore(checkpoints.resource)
            conversations.claim(
                "conversation-fencing",
                tenant_id="tenant-a",
                user_id="alice",
                ttl_seconds=60,
                now_ms=1000,
            )
            runs = PostgresRequestRunStore(checkpoints.resource)
            submitted, _ = runs.submit(
                tenant_id="tenant-a",
                request_id="request-fencing",
                conversation_id="conversation-fencing",
                user_id="alice",
                question="question",
                constraints={},
                graph_version="graph2-bounded-v1",
                input_schema_version=1,
                max_attempts=3,
                recovery_window_seconds=60,
                now_ms=1000,
            )
            old_owner = runs.claim(
                submitted.tenant_id,
                submitted.request_id,
                owner="old-owner",
                lease_seconds=1,
                now_ms=1000,
            )
            new_owner = runs.claim(
                submitted.tenant_id,
                submitted.request_id,
                owner="new-owner",
                lease_seconds=10,
                now_ms=2001,
            )
            self.assertIsNotNone(old_owner)
            self.assertIsNotNone(new_owner)
            with self.assertRaises(RunLeaseLostError):
                runs.finalize(
                    old_owner,
                    response={"answer": "stale"},
                    question="question",
                    conversation_ttl_seconds=60,
                    summary_max_chars=2000,
                    now_ms=2002,
                )
            finalized = runs.finalize(
                new_owner,
                response={
                    "request_id": "request-fencing",
                    "conversation_id": "conversation-fencing",
                    "answer": "fresh",
                    "citations": [],
                    "usage": {},
                    "component_versions": {"graph": "graph2-bounded-v1"},
                },
                question="question",
                conversation_ttl_seconds=60,
                summary_max_chars=2000,
                now_ms=2002,
            )
            self.assertEqual(finalized.status, RunStatus.SUCCEEDED)
            with checkpoints.resource.connection() as connection:
                count = connection.execute(
                    "SELECT COUNT(*) AS count FROM rag_conversation_turns WHERE request_id = %s",
                    ("request-fencing",),
                ).fetchone()["count"]
            self.assertEqual(count, 1)
            self.assertEqual(
                conversations.get(
                    "conversation-fencing",
                    tenant_id="tenant-a",
                    user_id="alice",
                    now_ms=2002,
                ).summary.count("fresh"),
                1,
            )
        finally:
            checkpoints.close()

    def test_retry_exhaustion_uses_stable_terminal_categories(self):
        checkpoints = create_checkpointer(self.settings)
        try:
            conversations = PostgresConversationStore(checkpoints.resource)
            conversations.claim(
                "conversation-exhausted",
                tenant_id="tenant-a",
                user_id="alice",
                ttl_seconds=60,
                now_ms=1000,
            )
            conversations.claim(
                "conversation-expired",
                tenant_id="tenant-a",
                user_id="alice",
                ttl_seconds=60,
                now_ms=1000,
            )
            runs = PostgresRequestRunStore(checkpoints.resource)
            exhausted, _ = runs.submit(
                tenant_id="tenant-a",
                request_id="request-exhausted",
                conversation_id="conversation-exhausted",
                user_id="alice",
                question="question",
                constraints={},
                graph_version="graph2-bounded-v1",
                input_schema_version=1,
                max_attempts=1,
                recovery_window_seconds=60,
                now_ms=1000,
            )
            claimed = runs.claim(
                exhausted.tenant_id,
                exhausted.request_id,
                owner="worker",
                lease_seconds=10,
                now_ms=1000,
            )
            terminal = runs.mark_retryable(
                claimed,
                error_category="EXECUTION_FAILED",
                retry_delay_seconds=1,
                now_ms=1001,
            )

            self.assertEqual(terminal.status, RunStatus.FAILED_TERMINAL)
            self.assertEqual(terminal.error_category, "MAX_ATTEMPTS_EXCEEDED")

            expired, _ = runs.submit(
                tenant_id="tenant-a",
                request_id="request-expired",
                conversation_id="conversation-expired",
                user_id="alice",
                question="question",
                constraints={},
                graph_version="graph2-bounded-v1",
                input_schema_version=1,
                max_attempts=3,
                recovery_window_seconds=1,
                now_ms=1000,
            )
            expired_claim = runs.claim(
                expired.tenant_id,
                expired.request_id,
                owner="worker",
                lease_seconds=10,
                now_ms=1000,
            )
            expired_terminal = runs.mark_retryable(
                expired_claim,
                error_category="EXECUTION_FAILED",
                retry_delay_seconds=1,
                now_ms=2001,
            )

            self.assertEqual(expired_terminal.status, RunStatus.EXPIRED)
            self.assertEqual(expired_terminal.error_category, "RECOVERY_EXPIRED")
        finally:
            checkpoints.close()

    def test_second_runtime_resumes_pending_node_and_publishes_recovered_result(self):
        recovery_settings = Settings(
            state_backend="postgres",
            database_url=DATABASE_URL,
            redis_url=REDIS_URL,
            recovery_enabled=True,
            db_pool_min_size=1,
            db_pool_max_size=4,
            conversation_lock_ttl_seconds=45,
            run_lease_seconds=10,
            run_heartbeat_seconds=1,
        )
        first = create_checkpointer(recovery_settings)
        second = None
        try:
            conversations = PostgresConversationStore(first.resource)
            runs = PostgresRequestRunStore(first.resource)
            first_runtime = SimpleNamespace(
                graph=build_recovery_graph(first.saver, fail_second=True),
                runs=runs,
                conversations=conversations,
                checkpoints=first,
                coordination=LocalConversationCoordinator(),
                settings=recovery_settings,
                resilience=None,
                telemetry=None,
            )
            command = make_command(
                question="question",
                conversation_id="conversation-recovery",
                request_id="request-recovery",
                constraints={},
            )
            identity = IdentityClaims("tenant-a", "alice", ("group:sales",))
            with self.assertRaises(ServiceExecutionError):
                RAGService(first_runtime).query(command, identity)
            with first.resource.connection() as connection, connection.transaction():
                connection.execute(
                    "UPDATE rag_request_runs SET next_retry_at_ms = 0 WHERE request_id = %s",
                    ("request-recovery",),
                )

            second = create_checkpointer(recovery_settings)
            second_runtime = SimpleNamespace(
                graph=build_recovery_graph(second.saver, fail_second=False),
                runs=PostgresRequestRunStore(second.resource),
                conversations=PostgresConversationStore(second.resource),
                checkpoints=second,
                coordination=LocalConversationCoordinator(),
                settings=recovery_settings,
                resilience=None,
                telemetry=None,
            )
            worker_service = RAGService(second_runtime)

            self.assertTrue(worker_service.recover_next(RecoveryResolver(), owner="worker-second-runtime"))
            recovered = second_runtime.runs.get("tenant-a", "request-recovery")
            snapshot = second_runtime.graph.get_state(
                {"configurable": {"thread_id": recovered.thread_id}}
            )
            self.assertEqual(recovered.status, RunStatus.SUCCEEDED)
            self.assertEqual(recovered.result["answer"], "recovered")
            self.assertEqual(snapshot.values["completed"], ["first", "second"])
        finally:
            if second is not None:
                second.close()
            first.close()


if __name__ == "__main__":
    unittest.main()
