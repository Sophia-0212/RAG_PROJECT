import re

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate

from llm_models.all_llm import get_llm
from rag_service.answer import AnswerResult
from rag_service.context import pack_context
from rag_service.retrieval import authorize_candidates, candidates_from_documents
from rag_service.security import RequestContext
from rag_service.settings import get_settings


def generate(state, model=None):
    """
    生成回答
    Args:
        state (dict): 当前图状态，包含问题和检索结果
    Returns:
        state (dict): 更新后的状态，新增包含生成结果的generation字段
    """
    question = state["question"]  # 获取用户问题
    documents = state["documents"]  # 获取检索到的文档
    hallucination_count = state.get("hallucination_count", 0)
    request_context = RequestContext.from_value(state.get("request_context"))
    candidates = state.get("candidates") or candidates_from_documents(documents)
    candidates = authorize_candidates(candidates, request_context)
    context_pack = pack_context(
        candidates,
        context=request_context,
        max_tokens=get_settings().context_max_tokens,
        parent_documents=state.get("parent_documents"),
    )

    if not context_pack.blocks:
        answer = "当前授权范围内没有足够证据回答该问题。"
        result = AnswerResult(answer=answer, refusal_reason="INSUFFICIENT_AUTHORIZED_EVIDENCE")
        return {
            "documents": [],
            "candidates": [],
            "question": question,
            "generation": answer,
            "answer_result": result.to_dict(),
            "context_pack": context_pack,
            "parent_documents": state.get("parent_documents", {}),
            "hallucination_count": hallucination_count,
        }

    prompt = PromptTemplate(
        template=(
            "你是企业知识库问答助手。只能使用给定上下文回答，不得补充上下文以外的事实。"
            "每个事实后必须使用对应的来源编号引用，例如[S1]。如果证据不足或冲突，明确拒绝回答。\n"
            "问题：{question}\n上下文：\n{context}\n回答："
        ),
        input_variables=["question", "context"],
    )

    # 构建RAG处理链
    rag_chain = (
            prompt |  # 第一步：使用提示模板
            (model or get_llm()) |  # 第二步：调用语言模型
            StrOutputParser()  # 第三步：解析模型输出为字符串
    )

    # RAG生成过程
    generation = rag_chain.invoke({"context": context_pack.render(), "question": question})
    cited_ids = set(re.findall(r"\[(S\d+)\]", generation))
    citations = tuple(
        citation for citation in context_pack.citations if citation.citation_id in cited_ids
    )
    result = AnswerResult(
        answer=generation,
        citations=citations,
        degraded=bool(state.get("retrieval_degraded", False)),
    )
    return {
        "documents": documents,
        "candidates": candidates,
        "question": question,
        "generation": generation,
        "answer_result": result.to_dict(),
        "context_pack": context_pack,
        "parent_documents": state.get("parent_documents", {}),
        "hallucination_count": hallucination_count + 1,
    }  # 返回更新后的状态，hallucination_count在每次(重新)生成后自增，供幻觉检测判断是否达到重试上限
