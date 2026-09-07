from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from rag_service.auth import (
    HttpRecoveryIdentityResolver,
    RecoveryAuthorizationDenied,
    RecoveryAuthorizationUnavailable,
)


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return io.BytesIO(json.dumps(self.payload).encode("utf-8"))

    def __exit__(self, exc_type, exc, traceback):
        return None


class RecoveryAuthorizationTest(unittest.TestCase):
    def setUp(self):
        self.resolver = HttpRecoveryIdentityResolver(
            "https://iam.internal/v1/recovery",
            "service-token",
        )

    def test_fresh_principals_are_returned(self):
        with patch(
            "rag_service.auth.urlopen",
            return_value=_Response(
                {
                    "allowed": True,
                    "tenant_id": "tenant-a",
                    "user_id": "alice",
                    "principal_ids": ["group:sales"],
                    "policy_version": "v2",
                }
            ),
        ):
            identity = self.resolver.resolve(
                tenant_id="tenant-a",
                user_id="alice",
                request_id="request-a",
            )

        self.assertEqual(identity.principal_ids, ("group:sales",))
        self.assertEqual(identity.policy_version, "v2")

    def test_explicit_denial_is_distinct_from_unavailability(self):
        with patch("rag_service.auth.urlopen", return_value=_Response({"allowed": False})):
            with self.assertRaises(RecoveryAuthorizationDenied):
                self.resolver.resolve(
                    tenant_id="tenant-a",
                    user_id="alice",
                    request_id="request-a",
                )
        with patch("rag_service.auth.urlopen", side_effect=URLError("offline")):
            with self.assertRaises(RecoveryAuthorizationUnavailable):
                self.resolver.resolve(
                    tenant_id="tenant-a",
                    user_id="alice",
                    request_id="request-a",
                )

    def test_http_forbidden_is_an_explicit_denial(self):
        forbidden = HTTPError(
            "https://iam.internal/v1/recovery",
            403,
            "forbidden",
            hdrs=None,
            fp=None,
        )
        with patch("rag_service.auth.urlopen", side_effect=forbidden):
            with self.assertRaises(RecoveryAuthorizationDenied):
                self.resolver.resolve(
                    tenant_id="tenant-a",
                    user_id="alice",
                    request_id="request-a",
                )


if __name__ == "__main__":
    unittest.main()
