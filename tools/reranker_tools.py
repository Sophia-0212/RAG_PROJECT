from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
from typing import Sequence

from sentence_transformers import CrossEncoder

from rag_service.settings import get_settings
from rag_service.resilience import CircuitBreaker, CircuitOpenError
from rag_service.retrieval import RetrievalCandidate, with_rerank_scores
from utils.log_utils import log


@lru_cache(maxsize=1)
def get_reranker() -> CrossEncoder:
    settings = get_settings()
    return CrossEncoder(settings.reranker_model, device=settings.model_device)


@lru_cache(maxsize=1)
def get_reranker_executor() -> ThreadPoolExecutor:
    return ThreadPoolExecutor(max_workers=2, thread_name_prefix="rag-reranker")


@lru_cache(maxsize=1)
def get_reranker_circuit() -> CircuitBreaker:
    settings = get_settings()
    return CircuitBreaker(
        failure_threshold=settings.circuit_failure_threshold,
        recovery_timeout_seconds=settings.circuit_recovery_seconds,
    )


@dataclass(frozen=True)
class RerankOutcome:
    candidates: tuple[RetrievalCandidate, ...]
    degraded: bool = False
    degradation_reason: str | None = None


def rerank_candidates(
    question: str,
    candidates: Sequence[RetrievalCandidate],
    *,
    top_n: int | None = None,
    timeout_seconds: float | None = None,
    reranker=None,
    circuit_breaker: CircuitBreaker | None = None,
) -> RerankOutcome:
    if not candidates:
        return RerankOutcome(candidates=())
    settings = get_settings()
    top_n = top_n or settings.rerank_top_n
    timeout_seconds = timeout_seconds or settings.reranker_timeout_seconds
    pairs = [[question, candidate.document.page_content] for candidate in candidates]
    breaker = circuit_breaker or get_reranker_circuit()
    try:
        breaker.before_call()
    except CircuitOpenError:
        return RerankOutcome(
            candidates=tuple(candidates[:top_n]),
            degraded=True,
            degradation_reason="RERANK_CIRCUIT_OPEN",
        )
    future = get_reranker_executor().submit((reranker or get_reranker()).predict, pairs)
    try:
        scores = future.result(timeout=timeout_seconds)
        ranked = with_rerank_scores(candidates, scores)
        breaker.record_success()
        return RerankOutcome(candidates=tuple(ranked[:top_n]))
    except TimeoutError:
        future.cancel()
        breaker.record_failure()
        log.warning("---Rerank超时，降级使用融合召回顺序---")
        return RerankOutcome(
            candidates=tuple(candidates[:top_n]),
            degraded=True,
            degradation_reason="RERANK_TIMEOUT",
        )
    except Exception as exc:
        breaker.record_failure()
        log.warning(f"---Rerank失败，降级使用融合召回顺序: {type(exc).__name__}---")
        return RerankOutcome(
            candidates=tuple(candidates[:top_n]),
            degraded=True,
            degradation_reason="RERANK_ERROR",
        )


def rerank_documents(question: str, documents: list, top_n: int | None = None, reranker=None) -> list:
    """
    用CrossEncoder对检索到的文档重新打分排序，取top_n

    Args:
        question: 用户问题
        documents: 待重排的文档列表(langchain Document)
        top_n: 重排后保留的文档数量

    Returns:
        list: 按相关性分数降序排列的前top_n篇文档
    """
    if not documents:
        return documents

    top_n = top_n or get_settings().rerank_top_n
    log.info(f"---Rerank精排: 候选{len(documents)}篇, 取top{top_n}---")
    candidates = [RetrievalCandidate(document=document, recall_rank=rank) for rank, document in enumerate(documents, 1)]
    outcome = rerank_candidates(
        question,
        candidates,
        top_n=top_n,
        reranker=reranker,
    )
    return [candidate.document for candidate in outcome.candidates]


def reset_reranker_cache() -> None:
    get_reranker.cache_clear()
    get_reranker_circuit.cache_clear()
