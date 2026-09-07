import unittest
from dataclasses import replace
from pathlib import Path

from evaluation.runner import Prediction, PredictionError, evaluate_predictions
from evaluation.schema import load_dataset


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET = PROJECT_ROOT / "evaluation" / "datasets" / "ad_crm_golden_small_v1.jsonl"


def perfect_prediction(case):
    if case.expected_action == "answer":
        answer = "；".join(fact.match_any[0] for fact in case.required_facts)
    elif case.expected_action == "clarify":
        answer = "；".join(case.clarification_points)
    else:
        answer = "请求不能处理。"
    return Prediction(
        case_id=case.case_id,
        action=case.expected_action,
        route=case.expected_route,
        answer=answer,
        retrieved_source_refs=tuple(
            sorted(case.graded_source_refs, key=case.graded_source_refs.get, reverse=True)
        ),
        cited_source_refs=case.expected_source_refs,
        reason_code=case.refusal_reason,
        latency_ms=100.0,
    )


class EvaluationRunnerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = load_dataset(DATASET)

    def test_perfect_predictions_generate_complete_slice_report(self):
        predictions = {case.case_id: perfect_prediction(case) for case in self.cases}

        report = evaluate_predictions(self.cases, predictions)

        self.assertEqual(report["case_count"], 64)
        self.assertEqual(report["metrics"]["case_pass_rate"], 1.0)
        self.assertEqual(report["metrics"]["acl_leakage_rate"], 0.0)
        self.assertEqual(report["failures"], [])
        self.assertEqual(set(report["slices"]["category"]), {case.category for case in self.cases})

    def test_missing_fact_and_forbidden_evidence_are_auditable_failures(self):
        predictions = {case.case_id: perfect_prediction(case) for case in self.cases}
        answer_case = next(case for case in self.cases if len(case.required_facts) > 1)
        acl_case = next(case for case in self.cases if case.category == "acl_negative")
        predictions[answer_case.case_id] = replace(predictions[answer_case.case_id], answer="信息不足")
        predictions[acl_case.case_id] = replace(
            predictions[acl_case.case_id],
            retrieved_source_refs=(acl_case.forbidden_source_refs[0],),
        )

        report = evaluate_predictions(self.cases, predictions)
        failures = {item["case_id"]: item for item in report["failures"]}

        self.assertIn(answer_case.case_id, failures)
        self.assertIn(acl_case.case_id, failures)
        self.assertLess(report["metrics"]["fact_coverage"], 1.0)
        self.assertGreater(report["metrics"]["acl_leakage_rate"], 0.0)

    def test_prediction_coverage_must_match_dataset(self):
        with self.assertRaisesRegex(PredictionError, "coverage mismatch"):
            evaluate_predictions(self.cases, {})


if __name__ == "__main__":
    unittest.main()
