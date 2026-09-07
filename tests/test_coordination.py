import threading
import time
import unittest

from rag_service.coordination import (
    CoordinationUnavailableError,
    ConversationBusyError,
    RedisConversationCoordinator,
    RedisTenantTokenBucket,
)
from rag_service.resilience import QuotaExceededError


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.quota = {}
        self.lock = threading.Lock()
        self.fail = False

    def set(self, key, value, *, nx=False, px=None):
        if self.fail:
            raise ConnectionError("unavailable")
        with self.lock:
            if nx and key in self.values:
                return False
            self.values[key] = value
            return True

    def eval(self, script, _keys, key, *args):
        if self.fail:
            raise ConnectionError("unavailable")
        with self.lock:
            if "updated_at" in script:
                remaining = self.quota.get(key, int(float(args[0])))
                if remaining <= 0:
                    return 0
                self.quota[key] = remaining - 1
                return 1
            token = args[0]
            if "PEXPIRE" in script:
                return 1 if self.values.get(key) == token else 0
            if self.values.get(key) == token:
                self.values.pop(key, None)
                return 1
            return 0

    def ping(self):
        if self.fail:
            raise ConnectionError("unavailable")
        return True

    def close(self):
        return None


class CoordinationTest(unittest.TestCase):
    def test_redis_quota_is_shared_by_independent_limiters(self):
        client = FakeRedis()
        first = RedisTenantTokenBucket(client, capacity=1, refill_per_second=0.01)
        second = RedisTenantTokenBucket(client, capacity=1, refill_per_second=0.01)

        first.acquire("tenant-a")

        with self.assertRaises(QuotaExceededError):
            second.acquire("tenant-a")
        second.acquire("tenant-b")

    def test_conversation_lock_rejects_a_second_holder_and_releases(self):
        client = FakeRedis()
        first = RedisConversationCoordinator(client, ttl_seconds=1, acquire_timeout_seconds=0.03)
        second = RedisConversationCoordinator(client, ttl_seconds=1, acquire_timeout_seconds=0.03)

        with first.slot("thread-1"):
            with self.assertRaises(ConversationBusyError):
                with second.slot("thread-1"):
                    pass

        with second.slot("thread-1"):
            pass

    def test_redis_failure_fails_closed(self):
        client = FakeRedis()
        client.fail = True
        quota = RedisTenantTokenBucket(client, capacity=1, refill_per_second=1)
        coordinator = RedisConversationCoordinator(client, ttl_seconds=1, acquire_timeout_seconds=0.01)

        with self.assertRaises(CoordinationUnavailableError):
            quota.acquire("tenant-a")
        with self.assertRaises(CoordinationUnavailableError):
            with coordinator.slot("thread-1"):
                pass
        self.assertFalse(coordinator.ping())

    def test_lost_lock_is_reported_when_release_token_no_longer_matches(self):
        client = FakeRedis()
        coordinator = RedisConversationCoordinator(client, ttl_seconds=1, acquire_timeout_seconds=0.01)

        with self.assertRaisesRegex(CoordinationUnavailableError, "ownership was lost"):
            with coordinator.slot("thread-1"):
                client.values.clear()


if __name__ == "__main__":
    unittest.main()
