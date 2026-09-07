import unittest
from pathlib import Path

from evaluation.gate import MetricRule, evaluate_gate, load_rules


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ReleaseGateTest(unittest.TestCase):
    def test_repository_gate_configuration_loads(self):
        rules = load_rules(PROJECT_ROOT / "evaluation" / "release_gate.json")

        self.assertEqual(len(rules), 19)
        self.assertEqual({rule.metric for rule in rules}, {
            "recall_at_10",
            "mrr",
            "ndcg_at_10",
            "citation_precision",
            "citation_recall",
            "fact_coverage",
            "action_accuracy",
            "route_accuracy",
            "clarification_coverage",
            "refusal_precision",
            "refusal_recall",
            "refusal_reason_accuracy",
            "high_risk_pass_rate",
            "acl_negative_pass_rate",
            "prompt_injection_pass_rate",
            "temporal_version_pass_rate",
            "security_pass_rate",
            "forbidden_fact_rate",
            "acl_leakage_rate",
        })

    def test_gate_reports_missing_and_out_of_range_metrics(self):
        rules = [
            MetricRule("quality", minimum=0.8),
            MetricRule("leakage", maximum=0.0),
            MetricRule("missing", minimum=1.0),
        ]

        report = evaluate_gate({"quality": 0.7, "leakage": 0.1}, rules)

        self.assertFalse(report.passed)
        self.assertEqual(len(report.failures), 3)

    def test_gate_passes_when_all_rules_are_met(self):
        rules = [MetricRule("quality", minimum=0.8), MetricRule("leakage", maximum=0.0)]

        report = evaluate_gate({"quality": 0.8, "leakage": 0.0}, rules)

        self.assertTrue(report.passed)
        self.assertEqual(report.failures, ())


if __name__ == "__main__":
    unittest.main()
