from langchain_core.tools import create_retriever_tool
from documents.milvus_db import MilvusVectorSave

mv = MilvusVectorSave()
mv.create_connection()
retriever = mv.vector_store_saved.as_retriever(
    search_type='similarity',  # 仅返回相似度超过阈值的文档
    search_kwargs={
        "k": 4,
        "score_threshold": 0.1,
        "ranker_type": "rrf",
        "ranker_params": {"k": 100},
        'filter': {"category": "content"}
    }
)


retriever_tool = create_retriever_tool(
    retriever,
    'rag_retriever',
    '搜索并返回关于 "CRM系统" 的信息, 内容涵盖：销售SOP流程、产品功能模块、系统操作与故障排查、客户异议处理话术等'
)