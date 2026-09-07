from __future__ import annotations

import hashlib
import threading
import time
from collections import OrderedDict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4

from rag_service.resilience import QuotaExceededError, TenantTokenBucket


class ConversationBusyError(RuntimeError):
    """Raised when another replica is already executing the conversation."""


class CoordinationUnavailableError(RuntimeError):
    """Raised when distributed coordination cannot be safely enforced."""


class QuotaLimiter(Protocol):
    def acquire(self, tenant_id: str) -> None: ...


class ConversationCoordinator(Protocol):
    @contextmanager
    def slot(self, thread_id: str) -> Iterator[None]: ...

    def ping(self) -> bool: ...

    def close(self) -> None: ...


@dataclass
class _LockEntry:
    lock: threading.Lock
    references: int = 0


class LocalConversationCoordinator:
    def __init__(self) -> None:
        self._locks: OrderedDict[str, _LockEntry] = OrderedDict()
        self._guard = threading.Lock()

    @contextmanager
    def slot(self, thread_id: str) -> Iterator[None]:
        with self._guard:
            entry = self._locks.setdefault(thread_id, _LockEntry(threading.Lock()))
            entry.references += 1
        try:
            with entry.lock:
                yield
        finally:
            with self._guard:
                entry.references -= 1
                if entry.references == 0:
                    self._locks.pop(thread_id, None)

    def ping(self) -> bool:
        return True

    def close(self) -> None:
        return None


_TOKEN_BUCKET_SCRIPT = """
local now_parts = redis.call('TIME')
local now = tonumber(now_parts[1]) + tonumber(now_parts[2]) / 1000000
local values = redis.call('HMGET', KEYS[1], 'tokens', 'updated_at')
local tokens = tonumber(values[1]) or tonumber(ARGV[1])
local updated_at = tonumber(values[2]) or now
tokens = math.min(tonumber(ARGV[1]), tokens + math.max(0, now - updated_at) * tonumber(ARGV[2]))
local allowed = 0
if tokens >= 1 then
  tokens = tokens - 1
  allowed = 1
end
redis.call('HSET', KEYS[1], 'tokens', tokens, 'updated_at', now)
redis.call('EXPIRE', KEYS[1], math.max(1, math.ceil(tonumber(ARGV[1]) / tonumber(ARGV[2]) * 2)))
return allowed
"""

_RENEW_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('PEXPIRE', KEYS[1], ARGV[2])
end
return 0
"""

_RELEASE_SCRIPT = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""


def _key(prefix: str, value: str) -> str:
    return f"rag:{prefix}:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


class RedisTenantTokenBucket:
    def __init__(self, client: Any, *, capacity: int, refill_per_second: float):
        self.client = client
        self.capacity = capacity
        self.refill_per_second = refill_per_second

    def acquire(self, tenant_id: str) -> None:
        try:
            allowed = self.client.eval(
                _TOKEN_BUCKET_SCRIPT,
                1,
                _key("quota", tenant_id),
                self.capacity,
                self.refill_per_second,
            )
        except Exception as exc:
            raise CoordinationUnavailableError("tenant quota store is unavailable") from exc
        if int(allowed) != 1:
            raise QuotaExceededError("tenant request quota exceeded")


class RedisConversationCoordinator:
    def __init__(
        self,
        client: Any,
        *,
        ttl_seconds: float,
        acquire_timeout_seconds: float,
    ):
        self.client = client
        self.ttl_ms = max(1, int(ttl_seconds * 1000))
        self.acquire_timeout_seconds = acquire_timeout_seconds

    @contextmanager
    def slot(self, thread_id: str) -> Iterator[None]:
        key = _key("conversation-lock", thread_id)
        token = uuid4().hex
        deadline = time.monotonic() + self.acquire_timeout_seconds
        acquired = False
        while time.monotonic() < deadline:
            try:
                acquired = bool(self.client.set(key, token, nx=True, px=self.ttl_ms))
            except Exception as exc:
                raise CoordinationUnavailableError("conversation coordination store is unavailable") from exc
            if acquired:
                break
            time.sleep(min(0.025, max(0.0, deadline - time.monotonic())))
        if not acquired:
            raise ConversationBusyError("conversation is already being processed")

        stop = threading.Event()
        lost = threading.Event()

        def renew() -> None:
            interval = max(0.05, self.ttl_ms / 3000)
            while not stop.wait(interval):
                try:
                    renewed = self.client.eval(_RENEW_SCRIPT, 1, key, token, self.ttl_ms)
                    if int(renewed) != 1:
                        lost.set()
                        return
                except Exception:
                    lost.set()
                    return

        thread = threading.Thread(target=renew, name="rag-conversation-lock-renewal", daemon=True)
        thread.start()
        body_error: BaseException | None = None
        try:
            yield
        except BaseException as exc:
            body_error = exc
            raise
        finally:
            stop.set()
            thread.join(timeout=1)
            try:
                released = self.client.eval(_RELEASE_SCRIPT, 1, key, token)
            except Exception:
                if body_error is None:
                    raise CoordinationUnavailableError("conversation lock release failed")
            else:
                if int(released) != 1 and body_error is None:
                    raise CoordinationUnavailableError("conversation lock ownership was lost")
            if lost.is_set() and body_error is None:
                raise CoordinationUnavailableError("conversation lock ownership was lost")

    def ping(self) -> bool:
        try:
            return bool(self.client.ping())
        except Exception:
            return False

    def close(self) -> None:
        self.client.close()


def create_coordination(settings):
    if settings.state_backend == "sqlite":
        return (
            LocalConversationCoordinator(),
            TenantTokenBucket(
                capacity=settings.tenant_request_burst,
                refill_per_second=settings.tenant_requests_per_minute / 60,
            ),
        )
    if not settings.redis_url:
        raise ValueError("RAG_REDIS_URL is required for the postgres state backend")
    from redis import Redis

    client = Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=settings.redis_socket_timeout_seconds,
        socket_timeout=settings.redis_socket_timeout_seconds,
        decode_responses=True,
    )
    coordinator = RedisConversationCoordinator(
        client,
        ttl_seconds=settings.conversation_lock_ttl_seconds,
        acquire_timeout_seconds=settings.conversation_lock_acquire_timeout_seconds,
    )
    quota = RedisTenantTokenBucket(
        client,
        capacity=settings.tenant_request_burst,
        refill_per_second=settings.tenant_requests_per_minute / 60,
    )
    return coordinator, quota
