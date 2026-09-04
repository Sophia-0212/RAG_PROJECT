from langchain_classic.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import RunnableWithMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory
from llm_models.all_llm import get_llm
from tools.retriever_tools import get_retriever_tool


def build_agent_with_history(history_store=None) -> RunnableWithMessageHistory:
    """Build the legacy tool-calling agent without executing external services."""
    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是一个智能助手，尽可能的调用工具回答用户的问题"),
        MessagesPlaceholder(variable_name="chat_history", optional=True),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad", optional=True),
    ])
    retriever_tool = get_retriever_tool()
    agent = create_tool_calling_agent(get_llm(), [retriever_tool], prompt)
    executor = AgentExecutor(agent=agent, tools=[retriever_tool])
    store = history_store if history_store is not None else {}

    def get_session_history(session_id: str) -> BaseChatMessageHistory:
        if session_id not in store:
            store[session_id] = ChatMessageHistory()
        return store[session_id]

    return RunnableWithMessageHistory(
        executor,
        get_session_history,
        input_messages_key="input",
        history_messages_key="chat_history",
    )


def main() -> None:
    from langfuse.langchain import CallbackHandler

    session_id = "local-cli"
    response = build_agent_with_history().invoke(
        {"input": "客户对价格有异议该怎么处理？"},
        config={
            "configurable": {"session_id": session_id},
            "callbacks": [CallbackHandler()],
            "metadata": {"langfuse_session_id": session_id, "langfuse_tags": ["rag_agent"]},
        },
    )
    print(response)


if __name__ == "__main__":
    main()
