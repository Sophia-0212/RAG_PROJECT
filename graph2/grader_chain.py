from functools import lru_cache

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from llm_models.all_llm import get_llm


# 数据模型 - 文档相关性评分
class GradeDocuments(BaseModel):
    """对检索到的文档进行相关性评分的二元判断"""

    binary_score: str = Field(
        description="文档是否与问题相关，取值为'yes'或'no'"
    )


# 提示词模板
system = """你是一个评估检索文档与用户问题相关性的评分器。\n 
    如果文档包含与用户问题相关的关键词或语义含义，则评为相关。\n
    不需要非常严格的测试，目的是过滤掉错误的检索结果。\n
    给出'yes'或'no'的二元评分来表示文档是否与问题相关。"""
grade_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", system),  # 系统角色提示
        ("human", "Retrieved document: \n\n {document} \n\n User question: {question}"),  # 用户输入模板
    ]
)

def build_retrieval_grader_chain(model):
    structured_llm_grader = model.with_structured_output(GradeDocuments)
    return grade_prompt | structured_llm_grader


@lru_cache(maxsize=1)
def get_retrieval_grader_chain():
    return build_retrieval_grader_chain(get_llm())
