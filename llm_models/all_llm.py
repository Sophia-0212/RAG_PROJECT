from langchain_community.tools import TavilySearchResults
from langchain_openai import ChatOpenAI

from utils.env_utils import OPENAI_API_KEY, DEEPSEEK_API_KEY, TAVILY_API_KEY

llm = ChatOpenAI(  # Ducc 内部网关
    temperature=0,
    model='gpt-5.5',
    api_key=OPENAI_API_KEY,
    base_url="https://oneapi-comate.baidu-int.com/v1")


web_search_tool = TavilySearchResults(max_results=2, tavily_api_key=TAVILY_API_KEY or "placeholder")

# llm = ChatOpenAI(
#     temperature=0.5,
#     model='deepseek-chat',
#     api_key=DEEPSEEK_API_KEY,
#     base_url="https://api.deepseek.com")