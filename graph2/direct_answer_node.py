from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate

from llm_models.all_llm import get_llm
from rag_service.answer import AnswerResult


def direct_answer(state, model=None):
    """
    不检索、不搜索，直接由大模型生成回答（适用于问候语、闲聊等无需外部信息的问题）
    Args:
        state (dict): 当前图状态，包含用户问题
    Returns:
        state (dict): 更新后的状态，新增包含生成结果的generation字段
    """
    question = state["question"]  # 获取用户问题

    prompt = PromptTemplate(
        template="你是一个友好的助手。请直接回答用户的问题。\n问题：{question} \n回答：",
        input_variables=["question"],
    )

    direct_chain = prompt | (model or get_llm()) | StrOutputParser()

    generation = direct_chain.invoke({"question": question})
    return {
        "question": question,
        "generation": generation,
        "answer_result": AnswerResult(answer=generation).to_dict(),
    }
