import unittest
from types import SimpleNamespace

from evaluation.performance import LoadSample, summarize_load
from graph2.graph_2 import build_graph
from rag_service.telemetry import MemoryEventSink, create_telemetry, redact_attributes


class TelemetryAndPerformanceTest(unittest.TestCase):
    def test_trace_redaction_is_allowlist_based(self):
        redacted = redact_attributes(
            {
                "request_id": "request-1",
                "action": "retrieve",
                "question": "sensitive question",
                "document_text": "secret document",
                "api_key": "secret-key",
            }
        )

        self.assertEqual(redacted, {"request_id": "request-1", "action": "retrieve"})

    def test_prometheus_labels_do_not_contain_tenant_or_user_ids(self):
        sink = MemoryEventSink()
        telemetry = create_telemetry(sink)
        telemetry.observe_request(
            elapsed_seconds=0.1,
            response={"refusal_reason": None, "degraded": False},
        )
        output = telemetry.metrics().decode("utf-8")

        self.assertIn("rag_requests_total", output)
        self.assertNotIn("tenant-a", output)
        self.assertNotIn("alice", output)

    def test_graph_action_trace_contains_lineage_but_not_question_text(self):
        sink = MemoryEventSink()
        telemetry = create_telemetry(sink)

        class Router:
            def invoke(self, _inputs):
                return SimpleNamespace(datasource="direct_answer")

        graph = build_graph(
            router_chain=Router(),
            telemetry=telemetry,
            node_overrides={
                "direct_answer": lambda state: {
                    "generation": "answer",
                    "answer_result": {"answer": "answer"},
                }
            },
        )
        graph.invoke(
            {
                "question": "sensitive customer question",
                "request_context": {
                    "request_id": "request-1",
                    "tenant_id": "tenant-a",
                    "user_id": "alice",
                },
            }
        )

        serialized = str(sink.events)
        self.assertIn("request-1", serialized)
        self.assertIn("direct_answer", serialized)
        self.assertNotIn("sensitive customer question", serialized)
        self.assertNotIn("tenant-a", serialized)

    def test_load_report_uses_observed_samples(self):
        report = summarize_load(
            [
                LoadSample(status_code=200, latency_ms=10),
                LoadSample(status_code=200, latency_ms=20),
                LoadSample(status_code=503, latency_ms=30, error_code="SERVICE_BUSY"),
            ],
            elapsed_seconds=1.5,
        )

        self.assertEqual(report["request_count"], 3)
        self.assertEqual(report["success_count"], 2)
        self.assertEqual(report["latency_ms"]["p95"], 30)
        self.assertEqual(report["errors"], {"SERVICE_BUSY": 1})


if __name__ == "__main__":
    unittest.main()
