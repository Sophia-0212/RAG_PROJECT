from graph2.grader_chain import get_retrieval_grader_chain
from utils.log_utils import log


def grade_documents(state, grader_chain=None):
    """
    评估检索到的文档与问题的相关性

    Args:
        state (dict): 当前图状态，包含问题和检索结果

    Returns:
        state (dict): 更新后的状态，documents字段仅保留相关文档
    """
    log.info("---CHECK DOCUMENT RELEVANCE TO QUESTION---")  # 打印当前阶段标识
    question = state["question"]  # 获取用户问题
    documents = state["documents"]  # 获取待评估文档

    # 文档评分与过滤
    filtered_docs = []  # 初始化相关文档列表
    grader_chain = grader_chain or get_retrieval_grader_chain()
    for d in documents:  # 遍历所有文档
        score = grader_chain.invoke(  # 调用评分器评估文档相关性
            {"question": question, "document": d.page_content}
        )
        grade = score.binary_score  # 获取二元评分结果
        if grade == "yes":  # 如果文档相关
            log.info("---GRADE: 打印相关标识---")  # 打印相关标识
            filtered_docs.append(d)  # 添加到相关文档列表
        else:  # 如果文档不相关
            log.info("---GRADE: 打印不相关标识,并丢掉doc---")  # 打印不相关标识
            continue  # 跳过当前文档
    relevant_chunk_ids = {document.metadata.get("chunk_id") for document in filtered_docs}
    candidates = [
        candidate
        for candidate in state.get("candidates", [])
        if candidate.document.metadata.get("chunk_id") in relevant_chunk_ids
    ]
    return {
        "documents": filtered_docs,
        "candidates": candidates,
        "question": question,
    }  # 返回仅含相关文档的状态
