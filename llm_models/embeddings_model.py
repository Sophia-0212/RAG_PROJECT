from langchain_openai import OpenAIEmbeddings
from langchain_huggingface import HuggingFaceEmbeddings
from utils.env_utils import OPENAI_API_KEY

openai_embedding = OpenAIEmbeddings(
    model="bge-large-zh",
    openai_api_key=OPENAI_API_KEY,
    openai_api_base="https://qianfan.baidubce.com/v2",
    check_embedding_ctx_length=False,
)

model_name = "BAAI/bge-small-zh-v1.5"
model_kwargs = {"device": "cpu"}
encode_kwargs = {"normalize_embeddings": True}
bge_embedding = HuggingFaceEmbeddings(
    model_name=model_name, model_kwargs=model_kwargs, encode_kwargs=encode_kwargs
)