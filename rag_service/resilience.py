from __future__ import annotations

import random
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, TypeVar


T = TypeVar("T")


class CircuitOpenError(RuntimeError):
    pass


class QuotaExceededError(RuntimeError):
    pass


class CapacityExceededError(RuntimeError):
    pass


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, *, failure_threshold: int, recovery_timeout_seconds: float, clock=time.monotonic):
        if failure_threshold <= 0 or recovery_timeout_seconds <= 0:
            raise ValueError("circuit breaker limits must be positive")
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.clock = clock
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._opened_at = 0.0
        self._probe_in_flight = False
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._state

    def before_call(self) -> None:
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return
            if self._state == CircuitState.OPEN:
                if self.clock() - self._opened_at < self.recovery_timeout_seconds:
                    raise CircuitOpenError("dependency circuit is open")
                self._state = CircuitState.HALF_OPEN
            if self._probe_in_flight:
                raise CircuitOpenError("dependency recovery probe is already running")
            self._probe_in_flight = True

    def record_success(self) -> None:
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failures = 0
            self._probe_in_flight = False

    def record_failure(self) -> None:
        with self._lock:
            self._probe_in_flight = False
            self._failures += 1
            if self._failures >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = self.clock()


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 2
    initial_backoff_seconds: float = 0.05
    max_backoff_seconds: float = 0.5
    jitter_ratio: float = 0.2

    def __post_init__(self) -> None:
        if self.max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        if self.initial_backoff_seconds < 0 or self.max_backoff_seconds < 0:
            raise ValueError("retry backoff cannot be negative")
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("jitter_ratio must be between zero and one")


def retry_call(
    operation: Callable[[], T],
    *,
    policy: RetryPolicy,
    retryable: Callable[[Exception], bool] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    random_value: Callable[[], float] = random.random,
) -> T:
    should_retry = retryable or (lambda _exc: True)
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return operation()
        except Exception as exc:
            if attempt >= policy.max_attempts or not should_retry(exc):
                raise
            base = min(
                policy.initial_backoff_seconds * (2 ** (attempt - 1)),
                policy.max_backoff_seconds,
            )
            jitter = base * policy.jitter_ratio * ((random_value() * 2) - 1)
            sleep(max(0.0, base + jitter))
    raise AssertionError("unreachable")


class DependencyGuard:
    def __init__(self, breaker: CircuitBreaker, retry_policy: RetryPolicy):
        self.breaker = breaker
        self.retry_policy = retry_policy

    def call(self, operation: Callable[[], T]) -> T:
        self.breaker.before_call()
        try:
            result = retry_call(operation, policy=self.retry_policy)
        except Exception:
            self.breaker.record_failure()
            raise
        self.breaker.record_success()
        return result


@dataclass
class _Bucket:
    tokens: float
    updated_at: float


class TenantTokenBucket:
    def __init__(
        self,
        *,
        capacity: int,
        refill_per_second: float,
        max_tenants: int = 10_000,
        clock=time.monotonic,
    ):
        if capacity <= 0 or refill_per_second <= 0 or max_tenants <= 0:
            raise ValueError("quota limits must be positive")
        self.capacity = capacity
        self.refill_per_second = refill_per_second
        self.clock = clock
        self.max_tenants = max_tenants
        self._buckets: OrderedDict[str, _Bucket] = OrderedDict()
        self._lock = threading.Lock()

    def acquire(self, tenant_id: str) -> None:
        now = self.clock()
        with self._lock:
            bucket = self._buckets.get(tenant_id)
            if bucket is None:
                if len(self._buckets) >= self.max_tenants:
                    self._buckets.popitem(last=False)
                bucket = _Bucket(float(self.capacity), now)
                self._buckets[tenant_id] = bucket
            else:
                self._buckets.move_to_end(tenant_id)
            elapsed = max(0.0, now - bucket.updated_at)
            bucket.tokens = min(self.capacity, bucket.tokens + elapsed * self.refill_per_second)
            bucket.updated_at = now
            if bucket.tokens < 1:
                raise QuotaExceededError("tenant request quota exceeded")
            bucket.tokens -= 1


class ConcurrencyLimiter:
    def __init__(self, *, capacity: int, acquire_timeout_seconds: float):
        if capacity <= 0 or acquire_timeout_seconds <= 0:
            raise ValueError("concurrency limits must be positive")
        self._semaphore = threading.BoundedSemaphore(capacity)
        self.acquire_timeout_seconds = acquire_timeout_seconds

    @contextmanager
    def slot(self) -> Iterator[None]:
        acquired = self._semaphore.acquire(timeout=self.acquire_timeout_seconds)
        if not acquired:
            raise CapacityExceededError("request concurrency capacity exceeded")
        try:
            yield
        finally:
            self._semaphore.release()


@dataclass
class RuntimeResilience:
    quota: Any
    concurrency: ConcurrencyLimiter
    dependency_guards: dict[str, DependencyGuard]

    def guard(self, dependency: str) -> DependencyGuard:
        return self.dependency_guards[dependency]
