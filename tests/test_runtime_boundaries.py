import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

from langchain_core.documents import Document

from documents.markdown_parser import MarkdownParser
from tools.reranker_tools import rerank_documents


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FakeSplitter:
    def split_documents(self, documents):
        return [Document(page_content="part-1"), Document(page_content="part-2")]


class FakeReranker:
    def predict(self, pairs):
        return [len(pair[1]) for pair in pairs]


class RuntimeBoundaryTest(unittest.TestCase):
    def test_parser_does_not_need_embedding_for_short_documents(self):
        parser = MarkdownParser(text_splitter=FakeSplitter(), semantic_chunk_min_chars=20)
        short = Document(page_content="short")

        self.assertEqual(parser.text_chunker([short]), [short])

    def test_parser_uses_injected_splitter_for_long_documents(self):
        parser = MarkdownParser(text_splitter=FakeSplitter(), semantic_chunk_min_chars=5)

        chunks = parser.text_chunker([Document(page_content="long content")])

        self.assertEqual([chunk.page_content for chunk in chunks], ["part-1", "part-2"])

    def test_reranker_can_be_tested_without_loading_a_model(self):
        documents = [Document(page_content="a"), Document(page_content="longer")]

        result = rerank_documents("question", documents, top_n=1, reranker=FakeReranker())

        self.assertEqual(result[0].page_content, "longer")

    def test_core_imports_and_graph_build_are_offline_safe(self):
        code = textwrap.dedent(
            """
            import importlib
            import socket

            def blocked(*args, **kwargs):
                raise AssertionError("network access attempted during import")

            socket.socket.connect = blocked
            modules = [
                "rag_service.settings",
                "llm_models.all_llm",
                "llm_models.embeddings_model",
                "documents.markdown_parser",
                "documents.milvus_db",
                "tools.retriever_tools",
                "tools.reranker_tools",
                "graph2.graph_2",
                "graph.graph1",
                "agent.rag_agent",
            ]
            for name in modules:
                importlib.import_module(name)
            from graph2.graph_2 import build_graph
            build_graph()
            """
        )
        environment = os.environ.copy()
        environment.pop("OPENAI_API_KEY", None)
        environment.pop("TAVILY_API_KEY", None)
        environment["MILVUS_URI"] = "http://127.0.0.1:1"
        environment["HF_HUB_OFFLINE"] = "1"

        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=PROJECT_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        self.assertEqual(result.returncode, 0, msg=result.stderr)


if __name__ == "__main__":
    unittest.main()
