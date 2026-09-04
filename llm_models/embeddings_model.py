import os
from functools import lru_cache

from langchain_openai import OpenAIEmbeddings
from langchain_huggingface import HuggingFaceEmbeddings

from rag_service.settings import get_settings


@lru_cache(maxsize=1)
def get_openai_embedding() -> OpenAIEmbeddings:
    """Create the API-backed embedding client on first use."""
    settings = get_settings()
    settings.require_llm()
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        openai_api_key=settings.openai_api_key,
        openai_api_base=settings.embedding_base_url,
        check_embedding_ctx_length=False,
    )


@lru_cache(maxsize=1)
def get_bge_embedding() -> HuggingFaceEmbeddings:
    """Load the local retrieval embedding model on first use."""
    settings = get_settings()
    if settings.hf_hub_offline:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
    return HuggingFaceEmbeddings(
        model_name=settings.local_embedding_model,
        model_kwargs={"device": settings.model_device},
        encode_kwargs={"normalize_embeddings": True},
    )


def reset_embedding_caches() -> None:
    get_openai_embedding.cache_clear()
    get_bge_embedding.cache_clear()
