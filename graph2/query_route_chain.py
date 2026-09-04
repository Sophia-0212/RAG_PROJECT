from functools import lru_cache
from typing import Literal

from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from llm_models.all_llm import get_llm


# 查询的动态路由： 根据用户的提问，决策采用哪种检索策略（网络检索，RAG）


# 数据模型
class RouteQuery(BaseModel):
    """将用户查询路由到最相关的数据源"""
    datasource: Literal["vectorstore", "web_search", "direct_answer"] = Field(
        ...,
        description="根据用户问题选择将其路由到向量知识库、网络搜索，或直接由大模型生成回答",
    )


# 提示词模板
system = """你是一个擅长将用户问题路由到合适数据源的专家，共有三种路由选择：

1. vectorstore（向量知识库）：知识库包含与CRM系统相关的文档，涵盖销售SOP流程、产品功能模块、
系统操作与故障排查、客户异议处理话术等。对于这些主题的问题请选择此项。
2. web_search（网络搜索）：问题不属于CRM知识库范围，但需要查询实时或外部世界的信息（比如天气、
新闻、通用知识问答）时选择此项。
3. direct_answer（直接生成）：问候语、寒暄、闲聊（比如"你好""你是谁""谢谢"）等不需要检索任何
外部信息，大模型可以直接回答的问题，选择此项。"""
route_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", system),  # 系统提示词
        ("human", "{question}"),  # 用户问题占位符
    ]
)

def build_question_router_chain(model):
    structured_llm_router = model.with_structured_output(RouteQuery)
    return route_prompt | structured_llm_router


@lru_cache(maxsize=1)
def get_question_router_chain():
    return build_question_router_chain(get_llm())


# 测试路由器
# print(  # 测试非CRM问题（应路由到网络搜索）
#     question_router_chain.invoke(
#         {"question": "今天，长沙的天气怎么样?"}
#     )
# )
# print(  # 测试CRM问题（应路由到向量数据库）
#     question_router_chain.invoke({"question": "客户对价格有异议该怎么处理？"})
# )
