import hashlib

from langchain_core.documents import Document

from documents.governance import SourceDocument, Visibility, govern_chunks
from llm_models.all_llm import get_web_search_tool
from rag_service.retrieval import candidates_from_documents
from rag_service.security import RequestContext
from utils.log_utils import log


def web_search(state, search_tool=None):
    """
    基于优化后的问题进行网络搜索

    Args:
        state (dict): 当前图状态，包含优化后的问题

    Returns:
        state (dict): 更新后的状态，documents字段替换为网络搜索结果
    """
    log.info("---WEB SEARCH---")  # 阶段标识
    question = state["question"]  # 获取优化后的问题
    request_context = RequestContext.from_value(state.get("request_context"))

    # 执行网络搜索
    docs = (search_tool or get_web_search_tool()).invoke({"query": question})  # 调用网络搜索工具
    web_documents = []
    for index, result in enumerate(docs):
        content = str(result.get("content", "")).strip()
        if not content:
            continue
        source_uri = str(result.get("url") or f"web:{hashlib.sha256(content.encode()).hexdigest()}")
        source = SourceDocument(
            tenant_id=request_context.tenant_id,
            source_uri=source_uri,
            content=content,
            title=str(result.get("title", source_uri)),
            visibility=Visibility.PUBLIC,
        )
        web_documents.extend(
            govern_chunks(
                source,
                [Document(page_content=content, metadata={"category": "content", "web_rank": index + 1})],
                ingestion_run_id=request_context.request_id,
                chunker_version="web-search-v1",
            )
        )

    return {
        "documents": web_documents,
        "candidates": candidates_from_documents(web_documents),
        "question": question,
    }  # 返回更新状态
