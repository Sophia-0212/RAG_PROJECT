from functools import lru_cache

from langchain_community.tools import TavilySearchResults
from langchain_openai import ChatOpenAI

from rag_service.settings import get_settings


@lru_cache(maxsize=1)
def get_llm() -> ChatOpenAI:
    """Create the configured chat model on first use."""
    settings = get_settings()
    settings.require_llm()
    return ChatOpenAI(
        temperature=0,
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        base_url=settings.llm_base_url,
        timeout=settings.llm_timeout_seconds,
        max_retries=0,
    )


@lru_cache(maxsize=1)
def get_web_search_tool() -> TavilySearchResults:
    """Create the external-search client on first use."""
    settings = get_settings()
    settings.require_web_search()
    return TavilySearchResults(max_results=2, tavily_api_key=settings.tavily_api_key)


def reset_model_caches() -> None:
    get_llm.cache_clear()
    get_web_search_tool.cache_clear()
