import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from langchain_core.documents import Document

from graph2.graph_2 import build_graph
from rag_service.checkpointing import create_sqlite_checkpointer
from rag_service.context import ContextPack
from rag_service.execution import (
    Action,
    ExecutionLimits,
    FailureReason,
    begin_action,
    initialize_execution,
    record_query,
)
from rag_service.retrieval import RetrievalCandidate


class FakeRouter:
    def __init__(self, route):
        self.route = route

    def invoke(self, _inputs):
        return SimpleNamespace(datasource=self.route)


def request(question="question", request_id="request-1"):
    return {
        "question": question,
        "request_context": {
            "request_id": request_id,
            "tenant_id": "tenant-a",
            "user_id": "alice",
            "principal_ids": [],
        },
    }


class ExecutionPolicyTest(unittest.TestCase):
    def test_action_budget_rejects_work_before_external_call(self):
        limits = ExecutionLimits(max_steps=2, max_retrieval_attempts=1)
        state = {**initialize_execution(request(), limits, now_ms=1000), "step_count": 1}

        allowed, first = begin_action(state, Action.RETRIEVE, now_ms=1001)
        allowed_again, second = begin_action({**state, **first}, Action.RETRIEVE, now_ms=1002)

        self.assertTrue(allowed)
        self.assertFalse(allowed_again)
        self.assertEqual(second["failure_reason"], FailureReason.STEP_BUDGET_EXCEEDED.value)

    def test_deadline_is_checked_before_work(self):
        state = initialize_execution(
            request(),
            ExecutionLimits(request_timeout_seconds=1),
            now_ms=1000,
        )

        allowed, update = begin_action(state, Action.GENERATE, now_ms=2000)

        self.assertFalse(allowed)
        self.assertEqual(update["failure_reason"], FailureReason.DEADLINE_EXCEEDED.value)

    def test_repeated_query_is_no_progress(self):
        state = initialize_execution(request("same question"), ExecutionLimits(), now_ms=1000)

        update = record_query(state, "  SAME   question ")

        self.assertEqual(update["failure_reason"], FailureReason.NO_PROGRESS.value)
        self.assertEqual(update["query_history"], ["same question"])

    def test_ambiguous_follow_up_without_history_requests_clarification(self):
        graph = build_graph(router_chain=FakeRouter("vectorstore"))

        result = graph.invoke(request("这个怎么处理？"))

        self.assertEqual(result["failure_reason"], FailureReason.CLARIFICATION_REQUIRED.value)
        self.assertEqual(
            result["answer_result"]["refusal_reason"],
            FailureReason.CLARIFICATION_REQUIRED.value,
        )

    def test_missing_request_identity_terminates_before_router(self):
        calls = []

        class RecordingRouter:
            def invoke(self, _inputs):
                calls.append("called")
                return SimpleNamespace(datasource="direct_answer")

        result = build_graph(router_chain=RecordingRouter()).invoke({"question": "hello"})

        self.assertEqual(result["failure_reason"], FailureReason.INVALID_REQUEST_CONTEXT.value)
        self.assertEqual(calls, [])

    def test_repeated_rewrite_path_terminates_with_reason(self):
        graph = build_graph(
            limits=ExecutionLimits(),
            router_chain=FakeRouter("vectorstore"),
            node_overrides={
                "retrieve": lambda state: {"documents": [], "candidates": []},
                "grade_documents": lambda state: {"documents": [], "candidates": []},
                "transform_query": lambda state: {"question": state["question"]},
            },
        )

        result = graph.invoke(request("same question"))

        self.assertEqual(result["failure_reason"], FailureReason.NO_PROGRESS.value)
        self.assertEqual(result["answer_result"]["refusal_reason"], FailureReason.NO_PROGRESS.value)
        self.assertEqual(result["original_question"], "same question")
        self.assertLessEqual(result["step_count"], result["execution_limits"]["max_steps"])

    def test_unsupported_generation_stops_at_generation_budget(self):
        graph = build_graph(
            limits=ExecutionLimits(max_generation_attempts=2),
            router_chain=FakeRouter("vectorstore"),
            node_overrides={
                "retrieve": lambda state: {"documents": ["evidence"], "candidates": []},
                "grade_documents": lambda state: {"documents": ["evidence"], "candidates": []},
                "generate": lambda state: {"generation": "unsupported", "documents": state["documents"]},
                "grade_generation": lambda state: {"generation_grade": "not_supported"},
            },
        )

        result = graph.invoke(request())

        self.assertEqual(result["generation_attempts"], 2)
        self.assertEqual(result["failure_reason"], FailureReason.GROUNDING_FAILED.value)

    def test_sqlite_checkpoint_survives_runtime_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "checkpoints.sqlite3")
            config = {"configurable": {"thread_id": "thread-1"}}
            overrides = {
                "direct_answer": lambda state: {
                    "generation": f"answer:{state['question']}",
                    "answer_result": {"answer": f"answer:{state['question']}"},
                }
            }

            first_handle = create_sqlite_checkpointer(path)
            first_graph = build_graph(
                checkpointer=first_handle.saver,
                router_chain=FakeRouter("direct_answer"),
                node_overrides=overrides,
            )
            first_graph.invoke(request("first", "request-1"), config=config)
            first_handle.close()

            second_handle = create_sqlite_checkpointer(path)
            try:
                second_graph = build_graph(
                    checkpointer=second_handle.saver,
                    router_chain=FakeRouter("direct_answer"),
                    node_overrides=overrides,
                )
                restored = second_graph.get_state(config)
                self.assertEqual(restored.values["generation"], "answer:first")

                second = second_graph.invoke(request("second", "request-2"), config=config)
                self.assertEqual(second["original_question"], "second")
                self.assertEqual(second["generation"], "answer:second")
                self.assertEqual(second["step_count"], 2)
            finally:
                second_handle.close()

    def test_strict_checkpoint_allowlist_restores_rag_state_types(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "rag-state.sqlite3")
            config = {"configurable": {"thread_id": "thread-rag-types"}}
            document = Document(page_content="evidence", metadata={"chunk_id": "chunk-1"})
            candidate = RetrievalCandidate(document=document, recall_rank=1)
            overrides = {
                "retrieve": lambda state: {"documents": [document], "candidates": [candidate]},
                "grade_documents": lambda state: {
                    "documents": state["documents"],
                    "candidates": state["candidates"],
                },
                "generate": lambda state: {
                    "generation": "supported",
                    "documents": state["documents"],
                    "candidates": state["candidates"],
                    "context_pack": ContextPack(blocks=(), token_count=0, truncated=False),
                },
                "grade_generation": lambda state: {"generation_grade": "useful"},
            }

            first = create_sqlite_checkpointer(path)
            graph = build_graph(
                checkpointer=first.saver,
                router_chain=FakeRouter("vectorstore"),
                node_overrides=overrides,
            )
            graph.invoke(request(), config=config)
            first.close()

            second = create_sqlite_checkpointer(path)
            try:
                restored = build_graph(checkpointer=second.saver).get_state(config).values
                self.assertIsInstance(restored["candidates"][0], RetrievalCandidate)
                self.assertIsInstance(restored["context_pack"], ContextPack)
            finally:
                second.close()


if __name__ == "__main__":
    unittest.main()
