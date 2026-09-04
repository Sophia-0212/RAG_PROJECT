import tempfile
import unittest
from pathlib import Path

from langchain_core.documents import Document

from documents.checkpoint import CheckpointError, JsonCheckpointStore
from documents.governance import (
    GovernanceError,
    SourceDocument,
    Visibility,
    govern_chunks,
)
from documents.index_release import AliasSwitchPlan, IndexReleaseError
from documents.ingestion_plan import IngestionManifest, OperationKind, plan_ingestion
from documents.ingestion_runner import IngestionExecutionError, execute_ingestion
from documents.manifest_store import JsonManifestStore
from documents.source_adapter import MarkdownSourceAdapter


def source(content="content", principals=("group:sales",), **overrides):
    values = {
        "tenant_id": "tenant-a",
        "source_uri": "sales/faq.md",
        "content": content,
        "title": "FAQ",
        "acl_principals": principals,
    }
    values.update(overrides)
    return SourceDocument(**values)


def chunks_for(item, text=None):
    return govern_chunks(
        item,
        [Document(page_content=text or item.content, metadata={"category": "content"})],
        ingestion_run_id="run-1",
        chunker_version="markdown-v1",
    )


class MemorySink:
    def __init__(self):
        self.upserts = []
        self.deletes = []

    def upsert(self, documents):
        self.upserts.append(tuple(document.metadata["chunk_id"] for document in documents))

    def delete(self, chunk_ids):
        self.deletes.append(tuple(chunk_ids))


class FailingSink(MemorySink):
    def upsert(self, documents):
        raise RuntimeError("temporary write failure")


class IngestionGovernanceTest(unittest.TestCase):
    def test_identity_is_stable_and_version_tracks_content_and_acl(self):
        original = source()
        same_acl_different_order = source(principals=("group:sales", "group:sales"))
        changed_content = source(content="new content")
        changed_acl = source(principals=("group:admin",))

        self.assertEqual(original.document_id, changed_content.document_id)
        self.assertEqual(original.version_id, same_acl_different_order.version_id)
        self.assertNotEqual(original.version_id, changed_content.version_id)
        self.assertNotEqual(original.version_id, changed_acl.version_id)

    def test_restricted_source_requires_acl(self):
        with self.assertRaisesRegex(GovernanceError, "ACL principal"):
            source(principals=())
        public = source(principals=(), visibility=Visibility.PUBLIC)
        self.assertEqual(public.acl_principals, ())

    def test_chunks_receive_stable_governance_metadata(self):
        item = source()

        first = chunks_for(item)
        second = chunks_for(item)

        self.assertEqual(first[0].metadata["chunk_id"], second[0].metadata["chunk_id"])
        self.assertEqual(first[0].metadata["tenant_id"], "tenant-a")
        self.assertEqual(first[0].metadata["version_id"], item.version_id)
        self.assertEqual(first[0].metadata["acl_principals"], ["group:sales"])

    def test_parent_relationship_is_converted_to_stable_chunk_id(self):
        item = source(content="parent child")
        governed = govern_chunks(
            item,
            [
                Document(page_content="parent", metadata={"element_id": "parent-element"}),
                Document(page_content="child", metadata={"parent_id": "parent-element"}),
            ],
            ingestion_run_id="run-1",
            chunker_version="markdown-v1",
        )

        self.assertEqual(governed[1].metadata["parent_chunk_id"], governed[0].metadata["chunk_id"])

    def test_new_unchanged_update_and_snapshot_delete_are_planned(self):
        original = source()
        original_chunks = chunks_for(original)
        empty = IngestionManifest(tenant_id="tenant-a")

        initial = plan_ingestion(
            run_id="initial",
            current=empty,
            incoming=[(original, original_chunks)],
        )
        self.assertEqual([op.kind for op in initial.operations], [OperationKind.UPSERT])

        unchanged = plan_ingestion(
            run_id="unchanged",
            current=initial.next_manifest,
            incoming=[(original, original_chunks)],
        )
        self.assertEqual(unchanged.operations, ())
        self.assertEqual(unchanged.unchanged_document_ids, (original.document_id,))

        updated_source = source(content="updated")
        updated_chunks = chunks_for(updated_source)
        updated = plan_ingestion(
            run_id="updated",
            current=initial.next_manifest,
            incoming=[(updated_source, updated_chunks)],
        )
        self.assertEqual(
            [op.kind for op in updated.operations],
            [OperationKind.UPSERT, OperationKind.DELETE],
        )
        self.assertEqual(updated.next_manifest.entries[original.document_id].version_id, updated_source.version_id)

        deleted = plan_ingestion(
            run_id="deleted",
            current=updated.next_manifest,
            incoming=[],
            authoritative_snapshot=True,
        )
        self.assertEqual([op.kind for op in deleted.operations], [OperationKind.DELETE])
        self.assertEqual(deleted.next_manifest.entries[original.document_id].status.value, "deleted")

    def test_checkpoint_resume_skips_completed_operations(self):
        item = source()
        chunks = chunks_for(item)
        plan = plan_ingestion(
            run_id="run-1",
            current=IngestionManifest(tenant_id="tenant-a"),
            incoming=[(item, chunks)],
        )

        with tempfile.TemporaryDirectory() as directory:
            store = JsonCheckpointStore(Path(directory) / "checkpoint.json")
            sink = MemorySink()
            first = execute_ingestion(plan, {item.version_id: chunks}, sink, store)
            second = execute_ingestion(plan, {item.version_id: chunks}, sink, store)

            self.assertEqual(first, second)
            self.assertEqual(len(sink.upserts), 1)
            with self.assertRaises(CheckpointError):
                store.start("other-run", "other-plan")

    def test_failed_operation_is_recorded_and_can_resume(self):
        item = source()
        chunks = chunks_for(item)
        plan = plan_ingestion(
            run_id="run-1",
            current=IngestionManifest(tenant_id="tenant-a"),
            incoming=[(item, chunks)],
        )

        with tempfile.TemporaryDirectory() as directory:
            store = JsonCheckpointStore(Path(directory) / "checkpoint.json")
            with self.assertRaises(IngestionExecutionError):
                execute_ingestion(plan, {item.version_id: chunks}, FailingSink(), store)
            failed = store.load()
            self.assertIn(plan.operations[0].operation_id, failed.failures)

            recovered_sink = MemorySink()
            recovered = execute_ingestion(plan, {item.version_id: chunks}, recovered_sink, store)

        self.assertEqual(recovered.failures, {})
        self.assertEqual(len(recovered_sink.upserts), 1)

    def test_manifest_round_trip_preserves_tombstones_and_generation(self):
        item = source()
        initial = plan_ingestion(
            run_id="run-1",
            current=IngestionManifest(tenant_id="tenant-a"),
            incoming=[(item, chunks_for(item))],
        )
        deleted = plan_ingestion(
            run_id="run-2",
            current=initial.next_manifest,
            incoming=[],
        )

        with tempfile.TemporaryDirectory() as directory:
            store = JsonManifestStore(Path(directory) / "manifest.json")
            store.save(deleted.next_manifest)
            loaded = store.load("tenant-a")

        self.assertEqual(loaded, deleted.next_manifest)

    def test_markdown_adapter_uses_relative_stable_source_uris(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / "sales"
            nested.mkdir()
            (nested / "faq.md").write_text("# Sales FAQ\n\nBody", encoding="utf-8")
            adapter = MarkdownSourceAdapter(root, "tenant-a", ("group:sales",))

            scanned = adapter.scan()

        self.assertEqual(len(scanned), 1)
        self.assertEqual(scanned[0][1].source_uri, "sales/faq.md")
        self.assertEqual(scanned[0][1].title, "Sales FAQ")

    def test_alias_switch_has_an_explicit_rollback_plan(self):
        switch = AliasSwitchPlan("rag_active", "rag_v1", "rag_v2")

        rollback = switch.rollback()

        self.assertEqual(rollback.current_collection, "rag_v2")
        self.assertEqual(rollback.target_collection, "rag_v1")
        with self.assertRaises(IndexReleaseError):
            AliasSwitchPlan("rag_active", None, "rag_v1").rollback()


if __name__ == "__main__":
    unittest.main()
