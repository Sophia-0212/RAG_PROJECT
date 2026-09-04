import tempfile
import unittest
from pathlib import Path

from rag_service.conversation import (
    ConversationAccessError,
    ConversationStore,
    scoped_thread_id,
)


class FakeCheckpointer:
    def __init__(self):
        self.deleted = []

    def delete_thread(self, thread_id):
        self.deleted.append(thread_id)


class ConversationStoreTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = str(Path(self.directory.name) / "conversations.sqlite3")
        self.store = ConversationStore(self.path)

    def tearDown(self):
        self.store.close()
        self.directory.cleanup()

    def test_conversation_is_tenant_scoped_and_user_owned(self):
        first = self.store.claim(
            "conversation-1",
            tenant_id="tenant-a",
            user_id="alice",
            ttl_seconds=60,
            now_ms=1000,
        )
        other_tenant = self.store.claim(
            "conversation-1",
            tenant_id="tenant-b",
            user_id="bob",
            ttl_seconds=60,
            now_ms=1000,
        )

        self.assertNotEqual(first.thread_id, other_tenant.thread_id)
        self.assertEqual(first.thread_id, scoped_thread_id("tenant-a", "conversation-1"))
        with self.assertRaises(ConversationAccessError):
            self.store.claim(
                "conversation-1",
                tenant_id="tenant-a",
                user_id="mallory",
                ttl_seconds=60,
                now_ms=1001,
            )

    def test_summary_is_bounded_and_persists_after_restart(self):
        self.store.append_turn(
            "conversation-1",
            tenant_id="tenant-a",
            user_id="alice",
            question="a long question",
            answer="a long answer",
            ttl_seconds=60,
            max_chars=18,
            now_ms=1000,
        )
        self.store.close()
        self.store = ConversationStore(self.path)

        restored = self.store.get(
            "conversation-1",
            tenant_id="tenant-a",
            user_id="alice",
            now_ms=1001,
        )

        self.assertLessEqual(len(restored.summary), 18)
        self.assertIn("long answer", restored.summary)

    def test_prune_deletes_metadata_and_graph_thread(self):
        record = self.store.claim(
            "conversation-1",
            tenant_id="tenant-a",
            user_id="alice",
            ttl_seconds=1,
            now_ms=1000,
        )
        checkpointer = FakeCheckpointer()

        count = self.store.prune_expired(checkpointer, now_ms=2000)

        self.assertEqual(count, 1)
        self.assertEqual(checkpointer.deleted, [record.thread_id])
        with self.assertRaises(KeyError):
            self.store.get(
                "conversation-1",
                tenant_id="tenant-a",
                user_id="alice",
                now_ms=2000,
            )


if __name__ == "__main__":
    unittest.main()
