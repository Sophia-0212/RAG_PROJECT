"""
把 测试文档集12篇/ 目录下的12篇CRM测试文档，解析+切块后写入独立的Milvus测试collection。
不影响生产collection t_collection01。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from pymilvus import IndexType, MilvusClient, Function
from pymilvus.client.types import MetricType, DataType, FunctionType
from langchain_milvus import Milvus, BM25BuiltInFunction

from documents.markdown_parser import MarkdownParser
from llm_models.embeddings_model import bge_embedding
from utils.env_utils import MILVUS_URI
from utils.log_utils import log

TEST_COLLECTION_NAME = "interview_recall_test"
DOCS_DIR = os.path.join(os.path.dirname(__file__), "测试文档集12篇")


def create_test_collection():
    client = MilvusClient(uri=MILVUS_URI)
    schema = client.create_schema()
    schema.add_field(field_name='id', datatype=DataType.INT64, is_primary=True, auto_id=True)
    schema.add_field(field_name='text', datatype=DataType.VARCHAR, max_length=6000, enable_analyzer=True,
                      analyzer_params={"tokenizer": "jieba", "filter": ["cnalphanumonly"]})
    schema.add_field(field_name='category', datatype=DataType.VARCHAR, max_length=1000)
    schema.add_field(field_name='source', datatype=DataType.VARCHAR, max_length=1000)
    schema.add_field(field_name='filename', datatype=DataType.VARCHAR, max_length=1000)
    schema.add_field(field_name='filetype', datatype=DataType.VARCHAR, max_length=1000)
    schema.add_field(field_name='title', datatype=DataType.VARCHAR, max_length=1000)
    schema.add_field(field_name='category_depth', datatype=DataType.INT64)
    schema.add_field(field_name='sparse', datatype=DataType.SPARSE_FLOAT_VECTOR, is_function_output=True)
    schema.add_field(field_name='dense', datatype=DataType.FLOAT_VECTOR, dim=512)

    bm25_function = Function(
        name="text_bm25_emb",
        input_field_names=["text"],
        output_field_names=["sparse"],
        function_type=FunctionType.BM25,
    )
    schema.add_function(bm25_function)
    index_params = client.prepare_index_params()

    index_params.add_index(
        field_name="sparse", index_name="sparse_inverted_index",
        index_type="SPARSE_INVERTED_INDEX", metric_type="BM25",
        params={"inverted_index_algo": "DAAT_MAXSCORE", "bm25_k1": 1.2, "bm25_b": 0.75},
    )
    index_params.add_index(
        field_name="dense", index_name="dense_inverted_index",
        index_type=IndexType.HNSW, metric_type=MetricType.IP,
        params={"M": 16, "efConstruction": 64}
    )

    if TEST_COLLECTION_NAME in client.list_collections():
        client.release_collection(collection_name=TEST_COLLECTION_NAME)
        client.drop_index(collection_name=TEST_COLLECTION_NAME, index_name='sparse_inverted_index')
        client.drop_index(collection_name=TEST_COLLECTION_NAME, index_name='dense_inverted_index')
        client.drop_collection(collection_name=TEST_COLLECTION_NAME)
        log.info(f"已清空旧的测试collection: {TEST_COLLECTION_NAME}")

    client.create_collection(
        collection_name=TEST_COLLECTION_NAME,
        schema=schema,
        index_params=index_params
    )
    log.info(f"测试collection创建完成: {TEST_COLLECTION_NAME}")


def main():
    create_test_collection()

    vector_store = Milvus(
        embedding_function=bge_embedding,
        collection_name=TEST_COLLECTION_NAME,
        builtin_function=BM25BuiltInFunction(),
        vector_field=['dense', 'sparse'],
        consistency_level="Strong",
        auto_id=True,
        connection_args={"uri": MILVUS_URI}
    )

    parser = MarkdownParser()
    md_files = sorted([f for f in os.listdir(DOCS_DIR) if f.endswith('.md')])
    log.info(f"共发现 {len(md_files)} 篇测试文档")

    total_chunks = 0
    for fname in md_files:
        fpath = os.path.join(DOCS_DIR, fname)
        docs = parser.parse_markdown_to_documents(fpath)
        # 只保留category=content的完整块（跟retriever_tools.py的filter策略一致）
        content_docs = [d for d in docs if d.metadata.get('category') == 'content']
        if content_docs:
            vector_store.add_documents(content_docs)
        total_chunks += len(content_docs)
        log.info(f"{fname}: 解析出 {len(docs)} 块，content类型 {len(content_docs)} 块")

    log.info(f"入库完成，共写入 {total_chunks} 个chunk")
    print(f"\n入库完成：{len(md_files)}篇文档，共{total_chunks}个chunk写入collection={TEST_COLLECTION_NAME}")


if __name__ == "__main__":
    main()
