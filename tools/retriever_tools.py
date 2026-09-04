from functools import lru_cache
import asyncio
import json
from dataclasses import dataclass
from typing import Any

from langchain_core.documents import Document
from langchain_core.tools import create_retriever_tool
from documents.milvus_db import MilvusVectorSave
from rag_service.settings import get_settings
from rag_service.security import RequestContext, is_document_authorized


@lru_cache(maxsize=1)
def get_vector_store():
    settings = get_settings()
    vector_store = MilvusVectorSave(settings=settings)
    vector_store.create_connection()
    if vector_store.vector_store_saved is None:
        raise RuntimeError("Milvus retriever initialization failed")
    return vector_store.vector_store_saved


@dataclass
class ScoredMilvusRetriever:
    vector_store: Any
    filter_expression: str
    settings: Any

    def invoke(self, query: str, config=None) -> list[Document]:
        if self.settings.fusion_mode == "weighted":
            ranker_type = "weighted"
            ranker_params = {"weights": [self.settings.dense_weight, self.settings.sparse_weight]}
        else:
            ranker_type = "rrf"
            ranker_params = {"k": self.settings.rrf_k}
        results = self.vector_store.similarity_search_with_score(
            query,
            k=self.settings.retrieval_top_k,
            fetch_k=self.settings.retrieval_top_k,
            expr=self.filter_expression,
            ranker_type=ranker_type,
            ranker_params=ranker_params,
        )
        documents = []
        for document, score in results:
            if score < self.settings.retrieval_score_threshold:
                continue
            metadata = dict(document.metadata)
            metadata["fused_score"] = float(score)
            documents.append(Document(page_content=document.page_content, metadata=metadata))
        return documents

    async def ainvoke(self, query: str, config=None) -> list[Document]:
        return await asyncio.to_thread(self.invoke, query, config)


def get_retriever(filter_expression: str | None = None):
    settings = get_settings()
    expression = filter_expression or 'tenant_id == "__deny_all_legacy_requests__"'
    return ScoredMilvusRetriever(
        vector_store=get_vector_store(),
        filter_expression=expression,
        settings=settings,
    )


def resolve_parent_documents(
    parent_chunk_ids: list[str],
    *,
    filter_expression: str,
    request_context: RequestContext,
) -> dict[str, Document]:
    normalized = sorted({chunk_id for chunk_id in parent_chunk_ids if chunk_id})
    if not normalized:
        return {}
    vector_store = get_vector_store()
    expression = (
        f"({filter_expression}) and "
        f"(chunk_id in {json.dumps(normalized, ensure_ascii=False)})"
    )
    output_fields = [
        "text",
        "category",
        "title",
        "tenant_id",
        "source_uri",
        "source_id",
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
        "chunker_version",
    ]
    rows = vector_store.client.query(
        collection_name=vector_store.collection_name,
        filter=expression,
        output_fields=output_fields,
    )
    resolved = {}
    for row in rows:
        metadata = {key: value for key, value in row.items() if key != "text"}
        document = Document(page_content=str(row.get("text", "")), metadata=metadata)
        if is_document_authorized(document, request_context):
            resolved[str(metadata.get("chunk_id"))] = document
    return resolved


def get_retriever_tool(filter_expression: str | None = None):
    return create_retriever_tool(
        get_retriever(filter_expression),
        "rag_retriever",
        '搜索并返回关于 "CRM系统" 的信息, 内容涵盖：销售SOP流程、产品功能模块、系统操作与故障排查、客户异议处理话术等',
        response_format="content_and_artifact",
    )


def reset_retriever_caches() -> None:
    get_vector_store.cache_clear()
