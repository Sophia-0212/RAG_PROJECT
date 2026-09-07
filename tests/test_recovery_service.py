from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from rag_service.auth import (
    IdentityClaims,
    RecoveryAuthorizationDenied,
    RecoveryAuthorizationUnavailable,
)
from rag_service.checkpointing import create_sqlite_checkpointer
from rag_service.conversation import ConversationStore
from rag_service.coordination import LocalConversationCoordinator
from rag_service.run_store import RequestRun, RunStatus, scoped_run_thread_id
from rag_service.service import RAGService, make_command
from rag_service.settings import Settings


def make_run(*, status: RunStatus = RunStatus.RECEIVED, result=None, lease_token=None) -> RequestRun:
    return RequestRun(
        tenant_id="tenant-a",
        request_id="request-a",
        conversation_id="conversation-a",
        user_id="alice",
        thread_id=scoped_run_thread_id("tenant-a", "conversation-a", "request-a"),
        input_hash="a" * 64,
        request_payload={"question": "question", "constraints": {}},
        status=status,
        graph_version="graph2-bounded-v1",
        input_schema_version=1,
        attempt_count=1 if lease_token else 0,
        max_attempts=3,
        lease_owner="owner" if lease_token else None,
        lease_token=lease_token,
        lease_until_ms=9999999999999 if lease_token else None,
        heartbeat_at_ms=None,
        submitted_at_ms=1,
        started_at_ms=1 if lease_token else None,
        updated_at_ms=1,
        completed_at_ms=2 if status == RunStatus.SUCCEEDED else None,
        recovery_expires_at_ms=9999999999999,
        next_retry_at_ms=0,
        result=result,
        error_category=None,
    )


class FakeRunStore:
    def __init__(self, run: RequestRun):
        self.run = run
        self.finalize_calls = 0

    def submit(self, **kwargs):
        return self.run, self.run.status == RunStatus.RECEIVED

    def claim(self, tenant_id, request_id, **kwargs):
        if self.run.status not in {RunStatus.RECEIVED, RunStatus.RETRYABLE}:
            return None
        self.run = replace(
            self.run,
            status=RunStatus.RUNNING,
            lease_token="lease-token",
            lease_owner=kwargs["owner"],
            attempt_count=self.run.attempt_count + 1,
        )
        return self.run

    def claim_next(self, **kwargs):
        return self.claim(self.run.tenant_id, self.run.request_id, **kwargs)

    def get(self, tenant_id, request_id):
        return self.run

    def heartbeat(self, run, **kwargs):
        return run.lease_token == self.run.lease_token

    def finalize(self, run, **kwargs):
        self.finalize_calls += 1
        self.run = replace(
            self.run,
            status=RunStatus.SUCCEEDED,
            result=dict(kwargs["response"]),
            lease_token=None,
            lease_owner=None,
        )
        return self.run

    def mark_retryable(self, run, **kwargs):
        self.run = replace(
            self.run,
            status=RunStatus.RETRYABLE,
            error_category=kwargs["error_category"],
            lease_token=None,
        )
        return self.run

    def mark_terminal(self, run, **kwargs):
        self.run = replace(
            self.run,
            status=kwargs["status"],
            error_category=kwargs["error_category"],
            lease_token=None,
        )
        return self.run

    def reconcile_expired(self):
        return 0


class FakeGraph:
    def __init__(self, *, values=None, next_nodes=()):
        self.values = dict(values or {})
        self.next = tuple(next_nodes)
        self.invocations = []
        self.updated = []

    def get_state(self, config):
        return SimpleNamespace(values=self.values, next=self.next)

    def update_state(self, config, values):
        self.updated.append(dict(values))
        self.values.update(values)

    def invoke(self, inputs, config, durability):
        self.invocations.append((inputs, config, durability))
        request_context = (
            dict(inputs["request_context"])
            if inputs is not None
            else dict(self.values["request_context"])
        )
        self.values = {
            **self.values,
            **(inputs or {}),
            "request_context": request_context,
            "active_request_id": request_context["request_id"],
            "answer_result": {"answer": "recovered answer", "citations": []},
            "component_versions": {"graph": "graph2-bounded-v1"},
            "step_count": int(self.values.get("step_count", 0)) + 1,
        }
        self.next = ()
        return self.values

    def stream(self, inputs, config, durability):
        state = self.invoke(inputs, config, durability)
        yield {"generate": state}


class Resolver:
    def resolve(self, **kwargs):
        return IdentityClaims("tenant-a", "alice", ("group:sales",), "policy-v2")


class DeniedResolver:
    def resolve(self, **kwargs):
        raise RecoveryAuthorizationDenied("denied")


class UnavailableResolver:
    def resolve(self, **kwargs):
        raise RecoveryAuthorizationUnavailable("unavailable")


class MismatchedResolver:
    def resolve(self, **kwargs):
        return IdentityClaims("tenant-b", "mallory", ("group:sales",), "policy-v2")


class RecoverableServiceTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        path = str(Path(self.directory.name) / "state.sqlite3")
        self.checkpoints = create_sqlite_checkpointer(path)
        self.conversations = ConversationStore(path)
        self.conversations.claim(
            "conversation-a",
            tenant_id="tenant-a",
            user_id="alice",
            ttl_seconds=60,
        )
        self.settings = Settings(
            checkpoint_path=path,
            recovery_enabled=True,
            run_lease_seconds=10,
            run_heartbeat_seconds=1,
        )
        self.identity = IdentityClaims("tenant-a", "alice", ("group:sales",))
        self.command = make_command(
            question="question",
            conversation_id="conversation-a",
            request_id="request-a",
            constraints={},
        )

    def tearDown(self):
        self.conversations.close()
        self.checkpoints.close()
        self.directory.cleanup()

    def service(self, graph, runs):
        runtime = SimpleNamespace(
            graph=graph,
            runs=runs,
            conversations=self.conversations,
            checkpoints=self.checkpoints,
            coordination=LocalConversationCoordinator(),
            settings=self.settings,
            resilience=None,
            telemetry=None,
        )
        return RAGService(runtime)

    def test_first_execution_uses_request_thread_sync_durability_and_reuses_result(self):
        runs = FakeRunStore(make_run())
        graph = FakeGraph()
        service = self.service(graph, runs)

        first = service.query(self.command, self.identity)
        second = service.query(self.command, self.identity)

        self.assertEqual(first["answer"], "recovered answer")
        self.assertEqual(second, first)
        self.assertEqual(len(graph.invocations), 1)
        inputs, config, durability = graph.invocations[0]
        self.assertIsNotNone(inputs)
        self.assertEqual(config["configurable"]["thread_id"], runs.run.thread_id)
        self.assertEqual(durability, "sync")
        self.assertEqual(runs.finalize_calls, 1)

    def test_recovery_resumes_pending_checkpoint_with_none_input(self):
        values = {
            "request_context": {
                "request_id": "request-a",
                "tenant_id": "tenant-a",
                "user_id": "alice",
            },
            "active_request_id": "request-a",
            "component_versions": {"graph": "graph2-bounded-v1"},
            "step_count": 4,
            "token_count": 100,
        }
        graph = FakeGraph(values=values, next_nodes=("generate",))
        runs = FakeRunStore(make_run(status=RunStatus.RETRYABLE))
        service = self.service(graph, runs)

        processed = service.recover_next(Resolver(), owner="worker-a")

        self.assertTrue(processed)
        self.assertIsNone(graph.invocations[0][0])
        self.assertEqual(graph.invocations[0][2], "sync")
        self.assertEqual(len(graph.updated), 1)
        self.assertEqual(runs.run.status, RunStatus.SUCCEEDED)

    def test_completed_snapshot_is_finalized_without_invoking_graph(self):
        response_state = {
            "request_context": {
                "request_id": "request-a",
                "tenant_id": "tenant-a",
                "user_id": "alice",
            },
            "active_request_id": "request-a",
            "component_versions": {"graph": "graph2-bounded-v1"},
            "answer_result": {"answer": "already complete", "citations": []},
        }
        graph = FakeGraph(values=response_state)
        runs = FakeRunStore(make_run(status=RunStatus.RETRYABLE))
        service = self.service(graph, runs)

        self.assertTrue(service.recover_next(Resolver(), owner="worker-a"))

        self.assertEqual(graph.invocations, [])
        self.assertEqual(runs.run.result["answer"], "already complete")

    def test_recovery_authorization_denial_is_terminal_without_graph_execution(self):
        graph = FakeGraph()
        runs = FakeRunStore(make_run(status=RunStatus.RETRYABLE))
        service = self.service(graph, runs)

        self.assertTrue(service.recover_next(DeniedResolver(), owner="worker-a"))

        self.assertEqual(runs.run.status, RunStatus.FAILED_TERMINAL)
        self.assertEqual(runs.run.error_category, "RECOVERY_AUTHORIZATION_DENIED")
        self.assertEqual(graph.invocations, [])

    def test_recovery_authorization_unavailability_is_retryable_without_graph_execution(self):
        graph = FakeGraph()
        runs = FakeRunStore(make_run(status=RunStatus.RETRYABLE))
        service = self.service(graph, runs)

        self.assertTrue(service.recover_next(UnavailableResolver(), owner="worker-a"))

        self.assertEqual(runs.run.status, RunStatus.RETRYABLE)
        self.assertEqual(runs.run.error_category, "RECOVERY_AUTHORIZATION_UNAVAILABLE")
        self.assertEqual(graph.invocations, [])

    def test_recovery_identity_mismatch_is_terminal_without_graph_execution(self):
        graph = FakeGraph()
        runs = FakeRunStore(make_run(status=RunStatus.RETRYABLE))
        service = self.service(graph, runs)

        self.assertTrue(service.recover_next(MismatchedResolver(), owner="worker-a"))

        self.assertEqual(runs.run.status, RunStatus.FAILED_TERMINAL)
        self.assertEqual(runs.run.error_category, "RECOVERY_AUTHORIZATION_DENIED")
        self.assertEqual(graph.invocations, [])

    def test_incompatible_graph_version_is_terminal_without_graph_execution(self):
        graph = FakeGraph()
        runs = FakeRunStore(
            replace(
                make_run(status=RunStatus.RETRYABLE),
                graph_version="graph2-incompatible-v0",
            )
        )
        service = self.service(graph, runs)

        self.assertTrue(service.recover_next(Resolver(), owner="worker-a"))

        self.assertEqual(runs.run.status, RunStatus.FAILED_TERMINAL)
        self.assertEqual(runs.run.error_category, "INCOMPATIBLE_GRAPH_VERSION")
        self.assertEqual(graph.invocations, [])

    def test_closing_durable_stream_marks_run_cancelled(self):
        graph = FakeGraph()
        runs = FakeRunStore(make_run())
        service = self.service(graph, runs)
        stream = service.stream(self.command, self.identity)

        first = next(stream)
        stream.close()

        self.assertEqual(first["type"], "progress")
        self.assertEqual(runs.run.status, RunStatus.CANCELLED)
        self.assertEqual(runs.run.error_category, "CLIENT_DISCONNECTED")


if __name__ == "__main__":
    unittest.main()
