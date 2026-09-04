import unittest

from langchain_core.documents import Document

from documents.index_release import IndexReleaseError
from documents.milvus_db import MilvusVectorSave
from rag_service.settings import Settings


class FakeSchema:
    def __init__(self):
        self.fields = []
        self.functions = []

    def add_field(self, **kwargs):
        self.fields.append(kwargs)

    def add_function(self, function):
        self.functions.append(function)


class FakeIndexParams:
    def __init__(self):
        self.indexes = []

    def add_index(self, **kwargs):
        self.indexes.append(kwargs)


class FakeMilvusClient:
    def __init__(self):
        self.collections = set()
        self.aliases = {}
        self.created = []
        self.dropped = []
        self.deletes = []

    def factory(self, **_kwargs):
        return self

    def has_collection(self, collection_name):
        return collection_name in self.collections

    def create_schema(self):
        return FakeSchema()

    def prepare_index_params(self):
        return FakeIndexParams()

    def create_collection(self, collection_name, schema, index_params):
        self.collections.add(collection_name)
        self.created.append((collection_name, schema, index_params))

    def drop_collection(self, collection_name):
        self.collections.remove(collection_name)
        self.dropped.append(collection_name)

    def list_aliases(self):
        return list(self.aliases)

    def describe_alias(self, alias):
        return {"collection_name": self.aliases[alias]}

    def create_alias(self, collection_name, alias):
        self.aliases[alias] = collection_name

    def alter_alias(self, collection_name, alias):
        self.aliases[alias] = collection_name

    def delete(self, collection_name, filter):
        self.deletes.append((collection_name, filter))


class FakeVectorStore:
    def __init__(self):
        self.added = []

    def add_documents(self, documents):
        self.added.append(tuple(documents))


class MilvusLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.client = FakeMilvusClient()
        self.settings = Settings(collection_name="rag_chunks")
        self.store = MilvusVectorSave(
            settings=self.settings,
            embedding=object(),
            client_factory=self.client.factory,
        )

    def test_create_collection_never_replaces_existing_data(self):
        self.client.collections.add("rag_chunks")

        created = self.store.create_collection()

        self.assertFalse(created)
        self.assertEqual(self.client.dropped, [])
        self.assertEqual(self.client.created, [])

    def test_new_collection_contains_governance_fields(self):
        self.assertTrue(self.store.ensure_collection())

        schema = self.client.created[0][1]
        field_names = {field["field_name"] for field in schema.fields}
        self.assertTrue(
            {
                "tenant_id",
                "document_id",
                "version_id",
                "chunk_id",
                "content_hash",
                "status",
                "visibility",
                "acl_principals",
                "effective_from_ms",
                "effective_to_ms",
                "ingestion_run_id",
            }.issubset(field_names)
        )

    def test_recreate_requires_exact_target_confirmation(self):
        self.client.collections.add("rag_chunks")
        with self.assertRaisesRegex(ValueError, "DROP:rag_chunks"):
            self.store.recreate_collection("yes")

        self.store.recreate_collection("DROP:rag_chunks")

        self.assertEqual(self.client.dropped, ["rag_chunks"])
        self.assertIn("rag_chunks", self.client.collections)

    def test_alias_switch_and_rollback_reject_stale_state(self):
        self.client.collections.update({"rag_v1", "rag_v2"})
        self.client.aliases["rag_active"] = "rag_v1"

        switch = self.store.activate_alias("rag_active", "rag_v2")
        self.assertEqual(self.client.aliases["rag_active"], "rag_v2")
        rollback = self.store.rollback_alias(switch)
        self.assertEqual(rollback.target_collection, "rag_v1")
        self.assertEqual(self.client.aliases["rag_active"], "rag_v1")

        switch = self.store.activate_alias("rag_active", "rag_v2")
        self.client.aliases["rag_active"] = "another_collection"
        with self.assertRaisesRegex(IndexReleaseError, "stale rollback"):
            self.store.rollback_alias(switch)

    def test_upsert_is_idempotent_by_governed_chunk_id(self):
        vector_store = FakeVectorStore()
        self.store.vector_store_saved = vector_store
        self.store.connected_collection_name = "rag_chunks"
        document = Document(page_content="content", metadata={"chunk_id": 'chunk-"1"'})

        self.store.upsert_documents([document])

        self.assertEqual(self.client.deletes, [("rag_chunks", 'chunk_id in ["chunk-\\"1\\""]')])
        self.assertEqual(vector_store.added, [(document,)])


if __name__ == "__main__":
    unittest.main()
