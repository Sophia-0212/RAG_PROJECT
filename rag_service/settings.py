from __future__ import annotations

import os
from pathlib import Path
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


class SettingsError(ValueError):
    """Raised when runtime configuration is missing or invalid."""


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise SettingsError(f"Expected a boolean value, got {value!r}")


def _as_int(value: str | None, default: int, name: str) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise SettingsError(f"{name} must be an integer") from exc
    if parsed <= 0:
        raise SettingsError(f"{name} must be greater than zero")
    return parsed


def _as_float(value: str | None, default: float, name: str) -> float:
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError as exc:
        raise SettingsError(f"{name} must be a number") from exc
    if not 0 <= parsed <= 1:
        raise SettingsError(f"{name} must be between 0 and 1")
    return parsed


def _as_positive_float(value: str | None, default: float, name: str) -> float:
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError as exc:
        raise SettingsError(f"{name} must be a number") from exc
    if parsed <= 0:
        raise SettingsError(f"{name} must be greater than zero")
    return parsed


@dataclass(frozen=True)
class Settings:
    environment: str = "development"
    openai_api_key: str | None = None
    deepseek_api_key: str | None = None
    tavily_api_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_public_key: str | None = None
    langfuse_base_url: str = "http://localhost:3001"
    milvus_uri: str = "http://127.0.0.1:19530"
    collection_name: str = "t_collection01"
    llm_model: str = "gpt-5.5"
    llm_base_url: str = "https://oneapi-comate.baidu-int.com/v1"
    embedding_model: str = "bge-large-zh"
    embedding_base_url: str = "https://qianfan.baidubce.com/v2"
    local_embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_dimension: int = 512
    reranker_model: str = "BAAI/bge-reranker-base"
    model_device: str = "cpu"
    hf_hub_offline: bool = True
    retrieval_top_k: int = 16
    rerank_top_n: int = 4
    retrieval_score_threshold: float = 0.0
    rrf_k: int = 100
    fusion_mode: str = "rrf"
    dense_weight: float = 0.5
    sparse_weight: float = 0.5
    reranker_timeout_seconds: float = 2.0
    context_max_tokens: int = 2048
    max_steps: int = 16
    max_retrieval_attempts: int = 3
    max_generation_attempts: int = 3
    max_query_transforms: int = 2
    max_web_searches: int = 1
    max_total_tokens: int = 8192
    request_timeout_seconds: float = 30.0
    checkpoint_path: str = ".rag-state/checkpoints.sqlite3"
    conversation_ttl_seconds: int = 86400
    conversation_summary_max_chars: int = 2000
    max_concurrent_requests: int = 8
    concurrency_acquire_timeout_seconds: float = 0.25
    tenant_request_burst: int = 20
    tenant_requests_per_minute: int = 60
    dependency_max_attempts: int = 2
    dependency_retry_initial_seconds: float = 0.05
    dependency_retry_max_seconds: float = 0.5
    circuit_failure_threshold: int = 3
    circuit_recovery_seconds: float = 30.0
    llm_timeout_seconds: float = 20.0
    gateway_shared_secret: str | None = None

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> "Settings":
        fusion_mode = values.get("RAG_FUSION_MODE", "rrf").strip().lower()
        if fusion_mode not in {"rrf", "weighted"}:
            raise SettingsError("RAG_FUSION_MODE must be 'rrf' or 'weighted'")
        dense_weight = _as_float(values.get("RAG_DENSE_WEIGHT"), 0.5, "RAG_DENSE_WEIGHT")
        sparse_weight = _as_float(values.get("RAG_SPARSE_WEIGHT"), 0.5, "RAG_SPARSE_WEIGHT")
        if dense_weight + sparse_weight <= 0:
            raise SettingsError("RAG_DENSE_WEIGHT and RAG_SPARSE_WEIGHT cannot both be zero")
        return cls(
            environment=values.get("RAG_ENV", "development"),
            openai_api_key=values.get("OPENAI_API_KEY") or None,
            deepseek_api_key=values.get("DEEPSEEK_API_KEY") or None,
            tavily_api_key=values.get("TAVILY_API_KEY") or None,
            langfuse_secret_key=values.get("LANGFUSE_SECRET_KEY") or None,
            langfuse_public_key=values.get("LANGFUSE_PUBLIC_KEY") or None,
            langfuse_base_url=values.get("LANGFUSE_BASE_URL", "http://localhost:3001"),
            milvus_uri=values.get("MILVUS_URI", "http://127.0.0.1:19530"),
            collection_name=values.get("RAG_COLLECTION_NAME", "t_collection01"),
            llm_model=values.get("RAG_LLM_MODEL", "gpt-5.5"),
            llm_base_url=values.get("RAG_LLM_BASE_URL", "https://oneapi-comate.baidu-int.com/v1"),
            embedding_model=values.get("RAG_EMBEDDING_MODEL", "bge-large-zh"),
            embedding_base_url=values.get("RAG_EMBEDDING_BASE_URL", "https://qianfan.baidubce.com/v2"),
            local_embedding_model=values.get("RAG_LOCAL_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5"),
            embedding_dimension=_as_int(
                values.get("RAG_EMBEDDING_DIMENSION"),
                512,
                "RAG_EMBEDDING_DIMENSION",
            ),
            reranker_model=values.get("RAG_RERANKER_MODEL", "BAAI/bge-reranker-base"),
            model_device=values.get("RAG_MODEL_DEVICE", "cpu"),
            hf_hub_offline=_as_bool(values.get("HF_HUB_OFFLINE"), True),
            retrieval_top_k=_as_int(values.get("RAG_RETRIEVAL_TOP_K"), 16, "RAG_RETRIEVAL_TOP_K"),
            rerank_top_n=_as_int(values.get("RAG_RERANK_TOP_N"), 4, "RAG_RERANK_TOP_N"),
            retrieval_score_threshold=_as_float(
                values.get("RAG_RETRIEVAL_SCORE_THRESHOLD"),
                0.0,
                "RAG_RETRIEVAL_SCORE_THRESHOLD",
            ),
            rrf_k=_as_int(values.get("RAG_RRF_K"), 100, "RAG_RRF_K"),
            fusion_mode=fusion_mode,
            dense_weight=dense_weight,
            sparse_weight=sparse_weight,
            reranker_timeout_seconds=_as_positive_float(
                values.get("RAG_RERANK_TIMEOUT_SECONDS"),
                2.0,
                "RAG_RERANK_TIMEOUT_SECONDS",
            ),
            context_max_tokens=_as_int(
                values.get("RAG_CONTEXT_MAX_TOKENS"),
                2048,
                "RAG_CONTEXT_MAX_TOKENS",
            ),
            max_steps=_as_int(values.get("RAG_MAX_STEPS"), 16, "RAG_MAX_STEPS"),
            max_retrieval_attempts=_as_int(
                values.get("RAG_MAX_RETRIEVAL_ATTEMPTS"),
                3,
                "RAG_MAX_RETRIEVAL_ATTEMPTS",
            ),
            max_generation_attempts=_as_int(
                values.get("RAG_MAX_GENERATION_ATTEMPTS"),
                3,
                "RAG_MAX_GENERATION_ATTEMPTS",
            ),
            max_query_transforms=_as_int(
                values.get("RAG_MAX_QUERY_TRANSFORMS"),
                2,
                "RAG_MAX_QUERY_TRANSFORMS",
            ),
            max_web_searches=_as_int(
                values.get("RAG_MAX_WEB_SEARCHES"),
                1,
                "RAG_MAX_WEB_SEARCHES",
            ),
            max_total_tokens=_as_int(
                values.get("RAG_MAX_TOTAL_TOKENS"),
                8192,
                "RAG_MAX_TOTAL_TOKENS",
            ),
            request_timeout_seconds=_as_positive_float(
                values.get("RAG_REQUEST_TIMEOUT_SECONDS"),
                30.0,
                "RAG_REQUEST_TIMEOUT_SECONDS",
            ),
            checkpoint_path=values.get("RAG_CHECKPOINT_PATH", ".rag-state/checkpoints.sqlite3"),
            conversation_ttl_seconds=_as_int(
                values.get("RAG_CONVERSATION_TTL_SECONDS"),
                86400,
                "RAG_CONVERSATION_TTL_SECONDS",
            ),
            conversation_summary_max_chars=_as_int(
                values.get("RAG_CONVERSATION_SUMMARY_MAX_CHARS"),
                2000,
                "RAG_CONVERSATION_SUMMARY_MAX_CHARS",
            ),
            max_concurrent_requests=_as_int(
                values.get("RAG_MAX_CONCURRENT_REQUESTS"),
                8,
                "RAG_MAX_CONCURRENT_REQUESTS",
            ),
            concurrency_acquire_timeout_seconds=_as_positive_float(
                values.get("RAG_CONCURRENCY_ACQUIRE_TIMEOUT_SECONDS"),
                0.25,
                "RAG_CONCURRENCY_ACQUIRE_TIMEOUT_SECONDS",
            ),
            tenant_request_burst=_as_int(
                values.get("RAG_TENANT_REQUEST_BURST"),
                20,
                "RAG_TENANT_REQUEST_BURST",
            ),
            tenant_requests_per_minute=_as_int(
                values.get("RAG_TENANT_REQUESTS_PER_MINUTE"),
                60,
                "RAG_TENANT_REQUESTS_PER_MINUTE",
            ),
            dependency_max_attempts=_as_int(
                values.get("RAG_DEPENDENCY_MAX_ATTEMPTS"),
                2,
                "RAG_DEPENDENCY_MAX_ATTEMPTS",
            ),
            dependency_retry_initial_seconds=_as_positive_float(
                values.get("RAG_DEPENDENCY_RETRY_INITIAL_SECONDS"),
                0.05,
                "RAG_DEPENDENCY_RETRY_INITIAL_SECONDS",
            ),
            dependency_retry_max_seconds=_as_positive_float(
                values.get("RAG_DEPENDENCY_RETRY_MAX_SECONDS"),
                0.5,
                "RAG_DEPENDENCY_RETRY_MAX_SECONDS",
            ),
            circuit_failure_threshold=_as_int(
                values.get("RAG_CIRCUIT_FAILURE_THRESHOLD"),
                3,
                "RAG_CIRCUIT_FAILURE_THRESHOLD",
            ),
            circuit_recovery_seconds=_as_positive_float(
                values.get("RAG_CIRCUIT_RECOVERY_SECONDS"),
                30.0,
                "RAG_CIRCUIT_RECOVERY_SECONDS",
            ),
            llm_timeout_seconds=_as_positive_float(
                values.get("RAG_LLM_TIMEOUT_SECONDS"),
                20.0,
                "RAG_LLM_TIMEOUT_SECONDS",
            ),
            gateway_shared_secret=values.get("RAG_GATEWAY_SHARED_SECRET") or None,
        )

    @classmethod
    def from_env(cls, load_env_file: bool = True) -> "Settings":
        if load_env_file:
            load_dotenv(override=False)
        return cls.from_mapping(os.environ)

    def require_llm(self) -> None:
        if not self.openai_api_key:
            raise SettingsError("OPENAI_API_KEY is required to create the configured LLM")

    def require_web_search(self) -> None:
        if not self.tavily_api_key:
            raise SettingsError("TAVILY_API_KEY is required to create the web-search tool")

    def validate_service_startup(self, *, identity_provider_configured: bool) -> None:
        if self.environment.strip().lower() != "production":
            return
        errors = []
        if not identity_provider_configured:
            errors.append("a production identity provider or RAG_GATEWAY_SHARED_SECRET is required")
        if not self.openai_api_key:
            errors.append("OPENAI_API_KEY is required")
        if self.gateway_shared_secret and len(self.gateway_shared_secret.strip()) < 32:
            errors.append("RAG_GATEWAY_SHARED_SECRET must contain at least 32 characters")
        if "127.0.0.1" in self.milvus_uri or "localhost" in self.milvus_uri:
            errors.append("MILVUS_URI cannot target localhost")
        if not Path(self.checkpoint_path).is_absolute():
            errors.append("RAG_CHECKPOINT_PATH must be an absolute persistent path")
        if errors:
            raise SettingsError("unsafe production configuration: " + "; ".join(errors))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings.from_env()
    os.environ.setdefault("LANGFUSE_HOST", settings.langfuse_base_url)
    return settings


def reset_settings_cache() -> None:
    """Clear cached configuration for tests and controlled runtime reloads."""
    get_settings.cache_clear()
