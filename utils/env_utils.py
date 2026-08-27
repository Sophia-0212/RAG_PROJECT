import os

from dotenv import load_dotenv

load_dotenv(override=True)

os.environ.setdefault('HF_HUB_OFFLINE', '1')

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
TAVILY_API_KEY = os.getenv('TAVILY_API_KEY')

MILVUS_URI = os.getenv('MILVUS_URI', 'http://127.0.0.1:19530')

COLLECTION_NAME = 't_collection01'
