from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from rag_service.checkpointing import create_sqlite_checkpointer


class _State(TypedDict, total=False):
    completed: list[str]
    deadline_at_ms: int


class LangGraphRecoverySemanticsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.handle = create_sqlite_checkpointer(str(Path(self.directory.name) / "state.sqlite3"))

    def tearDown(self) -> None:
        self.handle.close()
        self.directory.cleanup()

    def _graph(self, *, fail_second: list[bool]):
        def first(state: _State) -> _State:
            return {"completed": [*state.get("completed", []), "first"]}

        def second(state: _State) -> _State:
            if fail_second[0]:
                raise RuntimeError("injected failure")
            return {"completed": [*state.get("completed", []), "second"]}

        workflow = StateGraph(_State)
        workflow.add_node("first", first)
        workflow.add_node("second", second)
        workflow.add_edge(START, "first")
        workflow.add_edge("first", "second")
        workflow.add_edge("second", END)
        return workflow.compile(checkpointer=self.handle.saver)

    def test_none_input_resumes_pending_node_without_replaying_completed_node(self) -> None:
        failure = [True]
        graph = self._graph(fail_second=failure)
        config = {"configurable": {"thread_id": "run-thread-a"}}

        with self.assertRaisesRegex(RuntimeError, "injected failure"):
            graph.invoke({"completed": []}, config=config, durability="sync")
        self.assertEqual(graph.get_state(config).next, ("second",))

        failure[0] = False
        state = graph.invoke(None, config=config, durability="sync")

        self.assertEqual(state["completed"], ["first", "second"])
        self.assertEqual(graph.get_state(config).next, ())

    def test_update_state_refreshes_deadline_without_clearing_pending_task(self) -> None:
        failure = [True]
        graph = self._graph(fail_second=failure)
        config = {"configurable": {"thread_id": "run-thread-b"}}

        with self.assertRaises(RuntimeError):
            graph.invoke(
                {"completed": [], "deadline_at_ms": 1},
                config=config,
                durability="sync",
            )
        refreshed = int(time.time() * 1000) + 30_000
        graph.update_state(config, {"deadline_at_ms": refreshed})

        snapshot = graph.get_state(config)
        self.assertEqual(snapshot.next, ("second",))
        self.assertEqual(snapshot.values["deadline_at_ms"], refreshed)
        failure[0] = False
        self.assertEqual(graph.invoke(None, config=config, durability="sync")["completed"], ["first", "second"])

    def test_request_thread_isolates_checkpoints(self) -> None:
        graph = self._graph(fail_second=[False])
        first = {"configurable": {"thread_id": "request-thread-1"}}
        second = {"configurable": {"thread_id": "request-thread-2"}}

        graph.invoke({"completed": []}, config=first, durability="sync")

        self.assertEqual(graph.get_state(first).values["completed"], ["first", "second"])
        self.assertEqual(graph.get_state(second).values, {})


if __name__ == "__main__":
    unittest.main()
