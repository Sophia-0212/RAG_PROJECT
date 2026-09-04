from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from typing import Any

from langchain_core.documents import Document
from langchain_milvus import BM25BuiltInFunction, Milvus
from pymilvus import Function, IndexType, MilvusClient
from pymilvus.client.types import DataType, FunctionType, MetricType

from documents.index_release import AliasSwitchPlan, IndexReleaseError
from llm_models.embeddings_model import get_bge_embedding
from rag_service.settings import Settings, get_settings


class MilvusVectorSave:
    """Governed Milvus collection lifecycle and document persistence."""

    def __init__(
        self,
        settings: Settings | None = None,
        embedding: Any = None,
        client_factory: Callable[..., Any] = MilvusClient,
    ) -> None:
        self.settings = settings or get_settings()
        self.embedding = embedding
        self.client_factory = client_factory
        self.vector_store_saved: Milvus | None = None
        self.connected_collection_name: str | None = None

    def _client(self):
        return self.client_factory(uri=self.settings.milvus_uri)

    def _build_schema(self, client):
        schema = client.create_schema()
        schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True, auto_id=True)
        schema.add_field(
            field_name="text",
            datatype=DataType.VARCHAR,
            max_length=6000,
            enable_analyzer=True,
            analyzer_params={
                "tokenizer": {
                    "type": "jieba",
                    "dict": ["_default_", "线索转商机", "SOP流程", "回款周期"],
                },
                "filter": [
                    "cnalphanumonly",
                    {
                        "type": "synonym",
                        "synonyms": [
                            "客户, 客户方, 甲方 => 客户",
                            "登录失败, 无法登录, 登不上",
                        ],
                        "expand": False,
                    },
                ],
            },
        )
        schema.add_field(field_name="category", datatype=DataType.VARCHAR, max_length=1000, nullable=True)
        schema.add_field(field_name="source", datatype=DataType.VARCHAR, max_length=1000, nullable=True)
        schema.add_field(field_name="filename", datatype=DataType.VARCHAR, max_length=1000, nullable=True)
        schema.add_field(field_name="filetype", datatype=DataType.VARCHAR, max_length=1000, nullable=True)
        schema.add_field(field_name="title", datatype=DataType.VARCHAR, max_length=1000, nullable=True)
        schema.add_field(field_name="category_depth", datatype=DataType.INT64, nullable=True)

        for field_name, max_length in (
            ("tenant_id", 128),
            ("source_uri", 2048),
            ("source_id", 64),
            ("document_id", 64),
            ("version_id", 64),
            ("chunk_id", 64),
            ("content_hash", 64),
            ("status", 32),
            ("visibility", 32),
            ("ingestion_run_id", 128),
            ("chunker_version", 128),
        ):
            schema.add_field(
                field_name=field_name,
                datatype=DataType.VARCHAR,
                max_length=max_length,
                nullable=True,
            )
        schema.add_field(field_name="chunk_index", datatype=DataType.INT64, nullable=True)
        schema.add_field(field_name="effective_from_ms", datatype=DataType.INT64, nullable=True)
        schema.add_field(field_name="effective_to_ms", datatype=DataType.INT64, nullable=True)
        schema.add_field(field_name="governance_schema_version", datatype=DataType.INT64, nullable=True)
        schema.add_field(field_name="acl_principals", datatype=DataType.JSON, nullable=True)
        schema.add_field(field_name="sparse", datatype=DataType.SPARSE_FLOAT_VECTOR, is_function_output=True)
        schema.add_field(
            field_name="dense",
            datatype=DataType.FLOAT_VECTOR,
            dim=self.settings.embedding_dimension,
        )

        schema.add_function(
            Function(
                name="text_bm25_emb",
                input_field_names=["text"],
                output_field_names=["sparse"],
                function_type=FunctionType.BM25,
            )
        )
        return schema

    @staticmethod
    def _build_indexes(client):
        index_params = client.prepare_index_params()
        index_params.add_index(
            field_name="sparse",
            index_name="sparse_inverted_index",
            index_type="SPARSE_INVERTED_INDEX",
            metric_type="BM25",
            params={
                "inverted_index_algo": "DAAT_MAXSCORE",
                "bm25_k1": 1.2,
                "bm25_b": 0.75,
            },
        )
        index_params.add_index(
            field_name="dense",
            index_name="dense_inverted_index",
            index_type=IndexType.HNSW,
            metric_type=MetricType.IP,
            params={"M": 16, "efConstruction": 64},
        )
        return index_params

    def ensure_collection(self, collection_name: str | None = None) -> bool:
        """Create a missing collection and never modify an existing one."""
        collection_name = collection_name or self.settings.collection_name
        client = self._client()
        if client.has_collection(collection_name=collection_name):
            return False
        client.create_collection(
            collection_name=collection_name,
            schema=self._build_schema(client),
            index_params=self._build_indexes(client),
        )
        return True

    def create_collection(self) -> bool:
        """Backward-compatible, non-destructive alias for ensure_collection."""
        return self.ensure_collection()

    def recreate_collection(self, confirmation: str, collection_name: str | None = None) -> None:
        """Explicitly replace a collection after an exact target confirmation."""
        collection_name = collection_name or self.settings.collection_name
        expected = f"DROP:{collection_name}"
        if confirmation != expected:
            raise ValueError(f"Destructive recreation requires confirmation {expected!r}")
        client = self._client()
        if client.has_collection(collection_name=collection_name):
            client.drop_collection(collection_name=collection_name)
        client.create_collection(
            collection_name=collection_name,
            schema=self._build_schema(client),
            index_params=self._build_indexes(client),
        )

    def create_versioned_collection(self, version: str) -> str:
        normalized = version.strip().replace("-", "_")
        if not re.fullmatch(r"[A-Za-z0-9_]+", normalized):
            raise ValueError("collection version may contain only letters, numbers, underscore, and hyphen")
        collection_name = f"{self.settings.collection_name}__{normalized}"
        self.ensure_collection(collection_name)
        return collection_name

    def activate_alias(self, alias: str, target_collection: str) -> AliasSwitchPlan | None:
        client = self._client()
        if not client.has_collection(collection_name=target_collection):
            raise IndexReleaseError(f"target collection does not exist: {target_collection}")
        if alias not in client.list_aliases():
            client.create_alias(collection_name=target_collection, alias=alias)
            return AliasSwitchPlan(alias=alias, current_collection=None, target_collection=target_collection)

        description = client.describe_alias(alias=alias)
        current_collection = description.get("collection_name")
        if current_collection == target_collection:
            return None
        client.alter_alias(collection_name=target_collection, alias=alias)
        return AliasSwitchPlan(
            alias=alias,
            current_collection=current_collection,
            target_collection=target_collection,
        )

    def rollback_alias(self, plan: AliasSwitchPlan) -> AliasSwitchPlan:
        rollback = plan.rollback()
        client = self._client()
        description = client.describe_alias(alias=plan.alias)
        if description.get("collection_name") != plan.target_collection:
            raise IndexReleaseError("alias target changed after release; refusing stale rollback")
        if not client.has_collection(collection_name=rollback.target_collection):
            raise IndexReleaseError("rollback collection no longer exists")
        client.alter_alias(collection_name=rollback.target_collection, alias=rollback.alias)
        return rollback

    def create_connection(self, collection_name: str | None = None) -> None:
        collection_name = collection_name or self.settings.collection_name
        embedding = self.embedding or get_bge_embedding()
        self.vector_store_saved = Milvus(
            embedding_function=embedding,
            collection_name=collection_name,
            builtin_function=BM25BuiltInFunction(),
            vector_field=["dense", "sparse"],
            consistency_level="Strong",
            auto_id=True,
            connection_args={"uri": self.settings.milvus_uri},
        )
        self.connected_collection_name = collection_name

    def add_documents(self, documents: Sequence[Document]) -> None:
        if self.vector_store_saved is None:
            raise RuntimeError("Milvus connection has not been created")
        self.vector_store_saved.add_documents(list(documents))

    def delete_by_chunk_ids(self, chunk_ids: Sequence[str]) -> None:
        normalized = sorted({chunk_id for chunk_id in chunk_ids if chunk_id})
        if not normalized:
            return
        collection_name = self.connected_collection_name or self.settings.collection_name
        expression = f"chunk_id in {json.dumps(normalized, ensure_ascii=False)}"
        self._client().delete(collection_name=collection_name, filter=expression)

    def upsert_documents(self, documents: Sequence[Document]) -> None:
        chunk_ids = [document.metadata.get("chunk_id", "") for document in documents]
        if not documents or any(not chunk_id for chunk_id in chunk_ids):
            raise ValueError("upsert requires governed documents with chunk_id metadata")
        self.delete_by_chunk_ids(chunk_ids)
        self.add_documents(documents)


class MilvusIngestionSink:
    def __init__(self, store: MilvusVectorSave):
        self.store = store

    def upsert(self, documents: Sequence[Document]) -> None:
        self.store.upsert_documents(documents)

    def delete(self, chunk_ids: Sequence[str]) -> None:
        self.store.delete_by_chunk_ids(chunk_ids)
