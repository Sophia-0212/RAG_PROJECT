from functools import lru_cache

from langchain_core.prompts import ChatPromptTemplate
from pydantic import Field, BaseModel

from llm_models.all_llm import get_llm


# 数据模型 - 回答质量评分
class GradeAnswer(BaseModel):
    """评估回答是否解决用户问题的二元评分模型"""

    binary_score: str = Field(
        description="回答是否解决了问题，取值为'yes'或'no'"
    )


# 提示词模板
system = """您是一个评估回答是否解决用户问题的评分器。\n
     给出'yes'或'no'的二元评分。'yes'表示:回答确实解决了该问题。"""
answer_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", system),  # 系统角色设定
        ("human", "用户问题: \n\n {question} \n\n 生成回答: {generation}"),  # 用户输入模板
    ]
)

def build_answer_grader_chain(model):
    structured_llm_grader = model.with_structured_output(GradeAnswer)
    return answer_prompt | structured_llm_grader


@lru_cache(maxsize=1)
def get_answer_grader_chain():
    return build_answer_grader_chain(get_llm())
