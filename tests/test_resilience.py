import unittest

from langchain_core.documents import Document

from rag_service.resilience import (
    CapacityExceededError,
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
    ConcurrencyLimiter,
    QuotaExceededError,
    RetryPolicy,
    TenantTokenBucket,
    retry_call,
)
from rag_service.retrieval import RetrievalCandidate
from tools.reranker_tools import rerank_candidates


class Clock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value


class FailingReranker:
    def __init__(self):
        self.calls = 0

    def predict(self, _pairs):
        self.calls += 1
        raise RuntimeError("failed")


class ResilienceTest(unittest.TestCase):
    def test_retry_is_bounded_and_uses_exponential_backoff(self):
        calls = []
        sleeps = []

        def operation():
            calls.append("call")
            if len(calls) < 3:
                raise TimeoutError()
            return "ok"

        result = retry_call(
            operation,
            policy=RetryPolicy(max_attempts=3, initial_backoff_seconds=0.1, max_backoff_seconds=1, jitter_ratio=0),
            sleep=sleeps.append,
        )

        self.assertEqual(result, "ok")
        self.assertEqual(len(calls), 3)
        self.assertEqual(sleeps, [0.1, 0.2])

    def test_circuit_opens_and_allows_one_recovery_probe(self):
        clock = Clock()
        breaker = CircuitBreaker(failure_threshold=2, recovery_timeout_seconds=10, clock=clock)
        breaker.record_failure()
        breaker.record_failure()

        self.assertEqual(breaker.state, CircuitState.OPEN)
        with self.assertRaises(CircuitOpenError):
            breaker.before_call()
        clock.value = 10
        breaker.before_call()
        self.assertEqual(breaker.state, CircuitState.HALF_OPEN)
        with self.assertRaises(CircuitOpenError):
            breaker.before_call()
        breaker.record_success()
        self.assertEqual(breaker.state, CircuitState.CLOSED)

    def test_tenant_quota_refills_without_cross_tenant_interference(self):
        clock = Clock()
        quota = TenantTokenBucket(capacity=1, refill_per_second=1, clock=clock)
        quota.acquire("tenant-a")
        with self.assertRaises(QuotaExceededError):
            quota.acquire("tenant-a")
        quota.acquire("tenant-b")
        clock.value = 1
        quota.acquire("tenant-a")

    def test_tenant_quota_registry_is_bounded(self):
        quota = TenantTokenBucket(capacity=1, refill_per_second=1, max_tenants=2)
        quota.acquire("tenant-a")
        quota.acquire("tenant-b")
        quota.acquire("tenant-c")

        self.assertEqual(list(quota._buckets), ["tenant-b", "tenant-c"])

    def test_concurrency_limiter_rejects_when_full(self):
        limiter = ConcurrencyLimiter(capacity=1, acquire_timeout_seconds=0.001)
        with limiter.slot():
            with self.assertRaises(CapacityExceededError):
                with limiter.slot():
                    pass

    def test_reranker_open_circuit_degrades_without_second_model_call(self):
        breaker = CircuitBreaker(failure_threshold=1, recovery_timeout_seconds=60)
        reranker = FailingReranker()
        candidates = [RetrievalCandidate(Document(page_content="evidence"), recall_rank=1)]

        first = rerank_candidates(
            "q",
            candidates,
            reranker=reranker,
            circuit_breaker=breaker,
        )
        second = rerank_candidates(
            "q",
            candidates,
            reranker=reranker,
            circuit_breaker=breaker,
        )

        self.assertEqual(first.degradation_reason, "RERANK_ERROR")
        self.assertEqual(second.degradation_reason, "RERANK_CIRCUIT_OPEN")
        self.assertEqual(reranker.calls, 1)


if __name__ == "__main__":
    unittest.main()
