from tools.retriever_tools import get_retriever, resolve_parent_documents
from tools.reranker_tools import rerank_candidates
from rag_service.settings import get_settings
from rag_service.retrieval import authorize_candidates, candidates_from_documents, deduplicate_candidates
from rag_service.security import QueryConstraints, RequestContext, build_milvus_filter
from utils.log_utils import log


def retrieve(state, retriever=None, reranker=None, parent_resolver=None):
    """
    检索相关文档
    Args:
        state (dict): 当前图状态，包含用户问题

    Returns:
        state (dict): 更新后的状态，新增包含检索结果的documents字段
    """
    log.info("---去知识库中检索文档---")  # 打印当前阶段标识
    question = state["question"]  # 从状态中获取用户问题
    request_context = RequestContext.from_value(state.get("request_context"))
    constraints = QueryConstraints.from_value(state.get("query_constraints"))
    filter_expression = build_milvus_filter(request_context, constraints)
    # 文档检索(RRF融合召回, k=16)
    active_retriever = retriever or get_retriever(filter_expression)
    documents = active_retriever.invoke(question)  # 调用检索器获取相关文档
    candidates = candidates_from_documents(documents)
    candidates = authorize_candidates(candidates, request_context)
    candidates = deduplicate_candidates(candidates)
    # Rerank精排, 取top4
    outcome = rerank_candidates(
        question,
        candidates,
        top_n=get_settings().rerank_top_n,
        reranker=reranker,
    )
    ranked_candidates = list(outcome.candidates)
    parent_chunk_ids = [
        str(candidate.document.metadata["parent_chunk_id"])
        for candidate in ranked_candidates
        if candidate.document.metadata.get("parent_chunk_id")
    ]
    resolver = parent_resolver or resolve_parent_documents
    parent_documents = resolver(
        parent_chunk_ids,
        filter_expression=filter_expression,
        request_context=request_context,
    ) if parent_chunk_ids else {}
    return {
        "documents": [candidate.document for candidate in ranked_candidates],
        "candidates": ranked_candidates,
        "question": question,
        "retrieval_filter": filter_expression,
        "retrieval_degraded": outcome.degraded,
        "degradation_reason": outcome.degradation_reason,
        "parent_documents": parent_documents,
    }
