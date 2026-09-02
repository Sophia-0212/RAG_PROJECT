import os

from dotenv import load_dotenv

load_dotenv(override=True)

os.environ.setdefault('HF_HUB_OFFLINE', '1')

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
TAVILY_API_KEY = os.getenv('TAVILY_API_KEY')

LANGFUSE_SECRET_KEY = os.getenv('LANGFUSE_SECRET_KEY')
LANGFUSE_PUBLIC_KEY = os.getenv('LANGFUSE_PUBLIC_KEY')
LANGFUSE_BASE_URL = os.getenv('LANGFUSE_BASE_URL', 'http://localhost:3001')
# langfuse SDK 读取的是 LANGFUSE_HOST，这里做一次别名映射
os.environ.setdefault('LANGFUSE_HOST', LANGFUSE_BASE_URL)

MILVUS_URI = os.getenv('MILVUS_URI', 'http://127.0.0.1:19530')

COLLECTION_NAME = 't_collection01'
