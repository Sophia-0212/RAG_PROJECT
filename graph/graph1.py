from typing import Literal

from langchain_core.prompts import PromptTemplate
from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import START, END
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from graph.agent_node import agent_node
from graph.generate_node import generate
from graph.get_human_message import get_last_human_message
from graph.graph_state1 import AgentState, Grade
from graph.rewrite_node import rewrite
from llm_models.all_llm import get_llm
from tools.reranker_tools import rerank_documents
from tools.retriever_tools import get_retriever_tool
from utils.log_utils import log
from utils.print_utils import _print_event




def grade_documents(state) -> Literal["generate", "rewrite"]:
    """
    对检索到的文档做rerank精排+逐篇相关性打分，判断是否有文档与问题相关。
    参数:
        state (messages): 当前状态
    返回:
        str: 判断结果，是否存在相关文档
    """
    log.info("---检查document的相关性---")
    #  带结构化输出的LLM
    llm_with_structured = get_llm().with_structured_output(Grade)

    # 提示模板
    prompt = PromptTemplate(
        template="""你是一个评估检索文档与用户问题相关性的评分器。\n
            这是检索到的文档：\n\n {context} \n\n
            这是用户的问题：{question} \n
            如果文档包含与用户问题相关的关键词或语义含义，则评为相关。\n
            给出二元评分 'yes' 或 'no' 来表示文档是否与问题相关。""",
        input_variables=["context", "question"],
    )

    # 处理链
    chain = prompt | llm_with_structured

    messages = state["messages"]
    last_message = messages[-1]

    question = get_last_human_message(messages).content
    documents = last_message.artifact  # ToolNode(response_format='content_and_artifact')回填的原始Document列表

    # Rerank精排，取top4
    reranked_docs = rerank_documents(question, documents, top_n=4)

    # 逐篇相关性评估，不相关的丢掉
    relevant_docs = []
    for doc in reranked_docs:
        scored_result = chain.invoke({"question": question, "context": doc.page_content})
        if scored_result.binary_score == "yes":
            relevant_docs.append(doc)

    if relevant_docs:
        log.info(f"---输出：{len(relevant_docs)}篇文档相关---")
        last_message.content = "\n\n".join(doc.page_content for doc in relevant_docs)
        return "generate"
    else:
        log.info("---输出：文档不相关---")
        return "rewrite"

def build_graph():
    """Build the legacy Graph 1 demo without running it during import."""
    workflow = StateGraph(AgentState)
    workflow.add_node("agent", agent_node)
    workflow.add_node("retrieve", ToolNode([get_retriever_tool()]))
    workflow.add_node("rewrite", rewrite)
    workflow.add_node("generate", generate)

    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges(
        "agent",
        tools_condition,
        {"tools": "retrieve", END: END},
    )
    workflow.add_conditional_edges("retrieve", grade_documents)
    workflow.add_edge("rewrite", "agent")
    workflow.add_edge("generate", END)
    return workflow.compile(checkpointer=MemorySaver())


def run_cli() -> None:
    import uuid

    from langfuse.langchain import CallbackHandler

    graph = build_graph()
    thread_id = str(uuid.uuid4())
    config = {
        "configurable": {"thread_id": thread_id},
        "callbacks": [CallbackHandler()],
        "metadata": {"langfuse_session_id": thread_id, "langfuse_tags": ["graph1"]},
    }
    printed = set()

    while True:
        question = input("用户：")
        if question.lower() in {"q", "exit", "quit"}:
            log.info("对话结束，拜拜！")
            break
        inputs = {"messages": [("user", question)]}
        for event in graph.stream(inputs, config=config, stream_mode="values"):
            _print_event(event, printed)


if __name__ == "__main__":
    run_cli()
