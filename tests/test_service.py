import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from rag_service.auth import IdentityClaims
from rag_service.conversation import ConversationStore, scoped_thread_id
from rag_service.service import RAGService, make_command
from rag_service.settings import Settings


class FakeGraph:
    def __init__(self):
        self.inputs = None
        self.config = None

    def invoke(self, inputs, config):
        self.inputs = inputs
        self.config = config
        return {
            **inputs,
            "answer_result": {
                "answer": "answer",
                "citations": [],
                "refusal_reason": None,
                "degraded": False,
            },
            "step_count": 3,
            "retrieval_attempts": 1,
            "generation_attempts": 1,
            "component_versions": {"graph": "test"},
        }


class FakeSaver:
    def __init__(self):
        self.deleted = []

    def delete_thread(self, thread_id):
        self.deleted.append(thread_id)


class ServiceBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        path = str(Path(self.directory.name) / "service.sqlite3")
        self.conversations = ConversationStore(path)
        self.graph = FakeGraph()
        self.saver = FakeSaver()
        runtime = SimpleNamespace(
            graph=self.graph,
            conversations=self.conversations,
            checkpoints=SimpleNamespace(saver=self.saver),
            settings=Settings(checkpoint_path=path),
        )
        self.service = RAGService(runtime)
        self.identity = IdentityClaims(
            tenant_id="tenant-a",
            user_id="alice",
            principal_ids=("group:sales",),
        )

    def tearDown(self):
        self.conversations.close()
        self.directory.cleanup()

    def test_query_propagates_all_security_and_workflow_context(self):
        command = make_command(
            question="question",
            conversation_id="conversation-1",
            request_id="request-1",
            constraints={"source_ids": ["source-1"], "version_ids": []},
        )

        result = self.service.query(command, self.identity)

        self.assertEqual(self.graph.inputs["request_context"]["tenant_id"], "tenant-a")
        self.assertEqual(self.graph.inputs["request_context"]["principal_ids"], ("group:sales",))
        self.assertEqual(self.graph.inputs["query_constraints"]["source_ids"], ["source-1"])
        self.assertEqual(
            self.graph.config["configurable"]["thread_id"],
            scoped_thread_id("tenant-a", "conversation-1"),
        )
        self.assertEqual(result["usage"]["steps"], 3)
        stored = self.conversations.get(
            "conversation-1",
            tenant_id="tenant-a",
            user_id="alice",
        )
        self.assertIn("question", stored.summary)
        self.assertIn("answer", stored.summary)

    def test_delete_removes_owned_checkpoint_thread(self):
        self.conversations.claim(
            "conversation-1",
            tenant_id="tenant-a",
            user_id="alice",
            ttl_seconds=60,
        )

        deleted = self.service.delete_conversation("conversation-1", self.identity)

        self.assertTrue(deleted)
        self.assertEqual(
            self.saver.deleted,
            [scoped_thread_id("tenant-a", "conversation-1")],
        )


if __name__ == "__main__":
    unittest.main()
