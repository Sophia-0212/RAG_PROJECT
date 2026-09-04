import time
import unittest

from langchain_core.documents import Document
from langchain_core.runnables import RunnableLambda

from documents.governance import SourceDocument, govern_chunks
from graph2.generate_node2 import generate
from graph2.retriever_node import retrieve
from graph2.web_search_node import web_search
from rag_service.context import pack_context
from rag_service.retrieval import RetrievalCandidate
from rag_service.security import (
    QueryConstraints,
    RequestContext,
    build_milvus_filter,
    is_document_authorized,
)
from tools.reranker_tools import rerank_candidates
from tools.retriever_tools import ScoredMilvusRetriever
from rag_service.settings import Settings


NOW = 2_000_000


def request_context(**overrides):
    values = {
        "request_id": "request-1",
        "tenant_id": "tenant-a",
        "user_id": "alice",
        "principal_ids": ("group:sales",),
        "now_ms": NOW,
    }
    values.update(overrides)
    return RequestContext(**values)


def governed_document(
    text="evidence",
    *,
    tenant="tenant-a",
    principals=("group:sales",),
    effective_from=0,
    effective_to=0,
):
    source = SourceDocument(
        tenant_id=tenant,
        source_uri="sales/faq.md",
        content=text,
        title="Sales FAQ",
        acl_principals=principals,
        effective_from_ms=effective_from,
        effective_to_ms=effective_to,
    )
    return govern_chunks(
        source,
        [Document(page_content=text, metadata={"category": "content"})],
        ingestion_run_id="run-1",
        chunker_version="markdown-v1",
    )[0]


class CharacterCounter:
    def count(self, text):
        return len(text)

    def truncate(self, text, max_tokens):
        return text[:max_tokens]


class FakeRetriever:
    def __init__(self, documents):
        self.documents = documents

    def invoke(self, _question):
        return self.documents


class FakeVectorStore:
    def __init__(self, results):
        self.results = results
        self.kwargs = None

    def similarity_search_with_score(self, query, **kwargs):
        self.kwargs = {"query": query, **kwargs}
        return self.results


class FakeReranker:
    def __init__(self, scores=None, error=None, delay=0):
        self.scores = scores or []
        self.error = error
        self.delay = delay

    def predict(self, _pairs):
        if self.delay:
            time.sleep(self.delay)
        if self.error:
            raise self.error
        return self.scores


class FakeSearch:
    def invoke(self, _query):
        return [{"url": "https://example.test/doc", "title": "External", "content": "web evidence"}]


class SecureRetrievalTest(unittest.TestCase):
    def test_filter_is_fail_closed_and_escapes_literals(self):
        context = request_context(tenant_id='tenant-"a')
        constraints = QueryConstraints(source_ids=('source-"1',), version_ids=("version-1",))

        expression = build_milvus_filter(context, constraints)

        self.assertIn('tenant_id == "tenant-\\"a"', expression)
        self.assertIn("json_contains_any(acl_principals", expression)
        self.assertIn('status == "active"', expression)
        self.assertIn("effective_to_ms", expression)
        self.assertIn('source_id in ["source-\\"1"]', expression)

    def test_post_retrieval_authorization_rejects_missing_wrong_and_expired_metadata(self):
        context = request_context()
        allowed = governed_document()
        wrong_tenant = governed_document(tenant="tenant-b")
        expired = governed_document(effective_to=NOW)
        missing = Document(page_content="legacy", metadata={})

        self.assertTrue(is_document_authorized(allowed, context))
        self.assertFalse(is_document_authorized(wrong_tenant, context))
        self.assertFalse(is_document_authorized(expired, context))
        self.assertFalse(is_document_authorized(missing, context))

    def test_retriever_drops_unauthorized_candidates_before_rerank(self):
        allowed = governed_document(text="allowed")
        denied = governed_document(text="denied", principals=("group:admin",))

        result = retrieve(
            {
                "question": "question",
                "request_context": request_context(),
            },
            retriever=FakeRetriever([denied, allowed]),
            reranker=FakeReranker(scores=[0.9]),
        )

        self.assertEqual([document.page_content for document in result["documents"]], ["allowed"])
        self.assertIn('tenant_id == "tenant-a"', result["retrieval_filter"])
        self.assertFalse(result["retrieval_degraded"])

    def test_scored_retriever_preserves_fusion_score_and_weight_configuration(self):
        high = governed_document(text="high")
        low = governed_document(text="low")
        vector_store = FakeVectorStore([(high, 0.8), (low, 0.05)])
        settings = Settings(
            fusion_mode="weighted",
            dense_weight=0.7,
            sparse_weight=0.3,
            retrieval_score_threshold=0.1,
        )
        retriever = ScoredMilvusRetriever(vector_store, "secure-filter", settings)

        documents = retriever.invoke("question")

        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].metadata["fused_score"], 0.8)
        self.assertEqual(vector_store.kwargs["expr"], "secure-filter")
        self.assertEqual(vector_store.kwargs["ranker_params"], {"weights": [0.7, 0.3]})

    def test_retriever_resolves_parent_with_the_same_security_filter(self):
        source = SourceDocument(
            tenant_id="tenant-a",
            source_uri="sales/parent.md",
            content="parent child",
            acl_principals=("group:sales",),
        )
        parent, child = govern_chunks(
            source,
            [
                Document(page_content="parent", metadata={"element_id": "parent"}),
                Document(page_content="child", metadata={"parent_id": "parent"}),
            ],
            ingestion_run_id="run-1",
            chunker_version="markdown-v1",
        )
        captured = {}

        def resolver(parent_ids, *, filter_expression, request_context):
            captured["ids"] = parent_ids
            captured["filter"] = filter_expression
            captured["tenant"] = request_context.tenant_id
            return {parent.metadata["chunk_id"]: parent}

        result = retrieve(
            {"question": "question", "request_context": request_context()},
            retriever=FakeRetriever([child]),
            reranker=FakeReranker(scores=[0.9]),
            parent_resolver=resolver,
        )

        self.assertEqual(captured["ids"], [parent.metadata["chunk_id"]])
        self.assertIn('tenant_id == "tenant-a"', captured["filter"])
        self.assertEqual(result["parent_documents"][parent.metadata["chunk_id"]], parent)

    def test_reranker_timeout_and_error_fall_back_to_recall_order(self):
        candidates = [
            RetrievalCandidate(governed_document(text="one"), recall_rank=1),
            RetrievalCandidate(governed_document(text="two"), recall_rank=2),
        ]

        timeout = rerank_candidates(
            "q",
            candidates,
            reranker=FakeReranker(scores=[0.1, 0.9], delay=0.02),
            timeout_seconds=0.001,
            top_n=2,
        )
        error = rerank_candidates(
            "q",
            candidates,
            reranker=FakeReranker(error=RuntimeError("failed")),
            top_n=2,
        )

        self.assertTrue(timeout.degraded)
        self.assertEqual(timeout.degradation_reason, "RERANK_TIMEOUT")
        self.assertEqual([item.recall_rank for item in timeout.candidates], [1, 2])
        self.assertEqual(error.degradation_reason, "RERANK_ERROR")

    def test_context_pack_is_authorized_bounded_and_citable(self):
        allowed = governed_document(text="short evidence")
        denied = governed_document(text="secret", principals=("group:admin",))
        candidates = [
            RetrievalCandidate(denied, recall_rank=1, rerank_score=1.0),
            RetrievalCandidate(allowed, recall_rank=2, rerank_score=0.9),
        ]

        packed = pack_context(
            candidates,
            context=request_context(),
            max_tokens=100,
            token_counter=CharacterCounter(),
        )

        self.assertEqual(len(packed.blocks), 1)
        self.assertLessEqual(packed.token_count, 100)
        self.assertEqual(packed.citations[0].version_id, allowed.metadata["version_id"])
        self.assertNotIn("secret", packed.render())

    def test_context_pack_expands_an_authorized_same_version_parent(self):
        source = SourceDocument(
            tenant_id="tenant-a",
            source_uri="sales/parent.md",
            content="parent child",
            acl_principals=("group:sales",),
        )
        parent, child = govern_chunks(
            source,
            [
                Document(page_content="parent evidence", metadata={"element_id": "parent"}),
                Document(page_content="child", metadata={"parent_id": "parent"}),
            ],
            ingestion_run_id="run-1",
            chunker_version="markdown-v1",
        )

        packed = pack_context(
            [RetrievalCandidate(child, recall_rank=1)],
            context=request_context(),
            max_tokens=200,
            token_counter=CharacterCounter(),
            parent_documents={parent.metadata["chunk_id"]: parent},
        )

        self.assertIn("parent evidence", packed.render())
        self.assertEqual(packed.citations[0].chunk_id, parent.metadata["chunk_id"])

    def test_generation_returns_exact_structured_citations(self):
        document = governed_document(text="客户需要在24小时内首次联系。")
        model = RunnableLambda(lambda _prompt: "应在24小时内首次联系。[S1]")

        result = generate(
            {
                "question": "多久联系？",
                "documents": [document],
                "candidates": [RetrievalCandidate(document, recall_rank=1, rerank_score=0.9)],
                "request_context": request_context(),
            },
            model=model,
        )

        citation = result["answer_result"]["citations"][0]
        self.assertEqual(citation["version_id"], document.metadata["version_id"])
        self.assertEqual(citation["chunk_id"], document.metadata["chunk_id"])

    def test_web_results_keep_url_and_public_provenance(self):
        result = web_search(
            {"question": "external", "request_context": request_context()},
            search_tool=FakeSearch(),
        )

        document = result["documents"][0]
        self.assertEqual(document.metadata["source_uri"], "https://example.test/doc")
        self.assertEqual(document.metadata["visibility"], "public")
        self.assertTrue(is_document_authorized(document, request_context()))


if __name__ == "__main__":
    unittest.main()
