import unittest
from types import SimpleNamespace

from fastapi.testclient import TestClient

from rag_service.api import create_app
from rag_service.auth import TrustedHeaderIdentityProvider
from rag_service.auth import GatewaySharedSecretIdentityProvider
from rag_service.conversation import ConversationRecord
from rag_service.coordination import ConversationBusyError, CoordinationUnavailableError
from rag_service.service import RequestPendingError, ServiceExecutionError
from rag_service.run_store import RunStatus


class FakeService:
    def __init__(self):
        self.commands = []
        self.identities = []
        self.fail = False
        self.coordination_error = None
        self.durable_recovery_enabled = False
        self.pending = False

    @staticmethod
    def response(command):
        return {
            "request_id": command.request_id,
            "conversation_id": command.conversation_id,
            "answer": "verified answer",
            "citations": [],
            "refusal_reason": None,
            "degraded": False,
            "usage": {"steps": 2},
            "component_versions": {"graph": "test"},
        }

    def query(self, command, identity):
        if self.coordination_error is not None:
            raise self.coordination_error
        if self.fail:
            raise ServiceExecutionError("internal detail")
        if self.pending:
            raise RequestPendingError(command.request_id, RunStatus.RUNNING)
        self.commands.append(command)
        self.identities.append(identity)
        return self.response(command)

    def stream(self, command, identity):
        self.commands.append(command)
        self.identities.append(identity)
        yield {"type": "progress", "request_id": command.request_id, "node": "retrieve"}
        yield {"type": "answer", "data": self.response(command)}

    def get_conversation(self, conversation_id, identity):
        return ConversationRecord(
            conversation_id=conversation_id,
            tenant_id=identity.tenant_id,
            user_id=identity.user_id,
            thread_id="opaque",
            summary="not exposed",
            updated_at_ms=1000,
            expires_at_ms=2000,
        )

    def delete_conversation(self, conversation_id, identity):
        return True

    def get_request(self, request_id, identity):
        return SimpleNamespace(
            request_id=request_id,
            conversation_id="conversation-1",
            status=RunStatus.SUCCEEDED,
            attempt_count=2,
            max_attempts=3,
            submitted_at_ms=1000,
            updated_at_ms=2000,
            completed_at_ms=2000,
            error_category=None,
            result=self.response(SimpleNamespace(request_id=request_id, conversation_id="conversation-1")),
        )

    def ready(self):
        return True

    def metrics(self):
        return b"rag_requests_total 1\n"


class ApiContractTest(unittest.TestCase):
    def setUp(self):
        self.service = FakeService()
        app = create_app(
            service=self.service,
            identity_provider=TrustedHeaderIdentityProvider(enabled=True),
        )
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()
        self.headers = {
            "X-Tenant-ID": "tenant-a",
            "X-User-ID": "alice",
            "X-Principal-ID": "group:sales, role:manager",
            "X-Request-ID": "request-123",
        }

    def tearDown(self):
        self.client_context.__exit__(None, None, None)

    def test_query_contract_propagates_identity_request_and_constraints(self):
        response = self.client.post(
            "/v1/query",
            headers=self.headers,
            json={
                "question": "CRM policy?",
                "conversation_id": "conversation-1",
                "constraints": {"source_ids": ["source-1"]},
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["request_id"], "request-123")
        self.assertEqual(response.headers["X-Request-ID"], "request-123")
        self.assertEqual(response.json()["answer"], "verified answer")
        self.assertEqual(self.service.commands[0].constraints["source_ids"], ["source-1"])
        self.assertEqual(self.service.identities[0].tenant_id, "tenant-a")
        self.assertEqual(
            self.service.identities[0].principal_ids,
            ("group:sales", "role:manager"),
        )

    def test_authentication_and_validation_use_stable_error_envelope(self):
        missing_auth = self.client.post("/v1/query", json={"question": "hello"})
        invalid_body = self.client.post("/v1/query", headers=self.headers, json={"question": ""})

        self.assertEqual(missing_auth.status_code, 401)
        self.assertEqual(missing_auth.json()["error"]["code"], "AUTHENTICATION_FAILED")
        self.assertEqual(invalid_body.status_code, 422)
        self.assertEqual(invalid_body.json()["error"]["code"], "VALIDATION_ERROR")
        self.assertTrue(missing_auth.json()["error"]["request_id"])

    def test_invalid_request_id_is_rejected_before_execution(self):
        response = self.client.post(
            "/v1/query",
            headers={**self.headers, "X-Request-ID": "bad request id"},
            json={"question": "hello"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "INVALID_REQUEST_ID")
        self.assertTrue(response.headers["X-Request-ID"])

    def test_internal_failures_do_not_leak_exception_details(self):
        self.service.fail = True

        response = self.client.post("/v1/query", headers=self.headers, json={"question": "hello"})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "DEPENDENCY_UNAVAILABLE")
        self.assertNotIn("internal detail", response.text)

    def test_distributed_coordination_errors_have_stable_contracts(self):
        self.service.coordination_error = ConversationBusyError("internal lock key")
        busy = self.client.post("/v1/query", headers=self.headers, json={"question": "hello"})
        self.service.coordination_error = CoordinationUnavailableError("redis.internal:6379")
        unavailable = self.client.post("/v1/query", headers=self.headers, json={"question": "hello"})

        self.assertEqual(busy.status_code, 409)
        self.assertEqual(busy.json()["error"]["code"], "CONVERSATION_BUSY")
        self.assertNotIn("internal lock key", busy.text)
        self.assertEqual(unavailable.status_code, 503)
        self.assertEqual(unavailable.json()["error"]["code"], "COORDINATION_UNAVAILABLE")
        self.assertNotIn("redis.internal", unavailable.text)

    def test_sse_stream_has_progress_answer_and_done_events(self):
        response = self.client.post(
            "/v1/query/stream",
            headers=self.headers,
            json={"question": "hello", "conversation_id": "conversation-1"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("event: progress", response.text)
        self.assertIn("event: answer", response.text)
        self.assertIn("event: done", response.text)
        self.assertNotIn("documents", response.text)

    def test_durable_query_requires_supplied_request_id_and_pending_returns_location(self):
        self.service.durable_recovery_enabled = True
        missing = self.client.post(
            "/v1/query",
            headers={"X-Tenant-ID": "tenant-a", "X-User-ID": "alice"},
            json={"question": "hello"},
        )
        self.service.pending = True
        pending = self.client.post("/v1/query", headers=self.headers, json={"question": "hello"})

        self.assertEqual(missing.status_code, 400)
        self.assertEqual(missing.json()["error"]["code"], "REQUEST_ID_REQUIRED")
        self.assertEqual(pending.status_code, 202)
        self.assertEqual(pending.headers["Location"], "/v1/requests/request-123")

    def test_request_status_returns_result_without_original_payload(self):
        response = self.client.get("/v1/requests/request-123", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "SUCCEEDED")
        self.assertEqual(response.json()["result"]["answer"], "verified answer")
        self.assertNotIn("question", response.json())

    def test_conversation_metadata_does_not_expose_summary(self):
        response = self.client.get("/v1/conversations/conversation-1", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("summary", response.json())
        self.assertEqual(response.json()["tenant_id"], "tenant-a")

    def test_dify_adapter_maps_only_supported_rag_inputs(self):
        response = self.client.post(
            "/integrations/dify/v1/query",
            headers=self.headers,
            json={
                "query": "CRM policy?",
                "conversation_id": "dify-conversation",
                "inputs": {"source_ids": ["source-1"], "version_ids": ["version-1"]},
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer"], "verified answer")
        self.assertEqual(response.json()["metadata"]["request_id"], "request-123")

    def test_openapi_contains_versioned_service_contract(self):
        schema = self.client.get("/openapi.json").json()

        self.assertIn("/v1/query", schema["paths"])
        self.assertIn("/v1/query/stream", schema["paths"])
        self.assertEqual(schema["info"]["version"], "1.0.0")

    def test_metrics_endpoint_uses_prometheus_content_type(self):
        response = self.client.get("/metrics")

        self.assertEqual(response.status_code, 200)
        self.assertIn("rag_requests_total", response.text)
        self.assertIn("text/plain", response.headers["content-type"])

    def test_readiness_returns_service_checks(self):
        response = self.client.get("/health/ready")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["checks"]["conversation_store"], "ok")

    def test_gateway_provider_requires_matching_bearer_secret(self):
        secret = "a-production-grade-gateway-secret-123"
        app = create_app(
            service=FakeService(),
            identity_provider=GatewaySharedSecretIdentityProvider(secret),
        )
        with TestClient(app) as client:
            denied = client.post(
                "/v1/query",
                headers={"X-Tenant-ID": "tenant-a", "X-User-ID": "alice"},
                json={"question": "hello"},
            )
            allowed = client.post(
                "/v1/query",
                headers={
                    "X-Tenant-ID": "tenant-a",
                    "X-User-ID": "alice",
                    "Authorization": f"Bearer {secret}",
                },
                json={"question": "hello"},
            )

        self.assertEqual(denied.status_code, 401)
        self.assertEqual(allowed.status_code, 200)

    def test_gateway_provider_rejects_weak_secret(self):
        with self.assertRaisesRegex(ValueError, "at least 32"):
            GatewaySharedSecretIdentityProvider("too-short")


if __name__ == "__main__":
    unittest.main()
