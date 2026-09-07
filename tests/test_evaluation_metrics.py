import unittest

from evaluation.metrics import (
    citation_precision,
    citation_recall,
    fact_coverage,
    forbidden_fact_rate,
    hit_rate_at_k,
    leakage_rate,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
)


class EvaluationMetricsTest(unittest.TestCase):
    def test_retrieval_metrics_are_bounded_and_deduplicated(self):
        retrieved = ["noise", "doc-a", "doc-a", "doc-b"]
        relevant = ["doc-a", "doc-b"]

        self.assertEqual(hit_rate_at_k(retrieved, relevant, 2), 1.0)
        self.assertEqual(recall_at_k(retrieved, relevant, 2), 0.5)
        self.assertEqual(recall_at_k(retrieved, relevant, 3), 1.0)
        self.assertEqual(reciprocal_rank(retrieved, relevant), 0.5)

    def test_citation_metrics_penalize_unsupported_sources(self):
        cited = ["doc-a", "doc-x"]

        self.assertEqual(citation_precision(cited, ["doc-a"]), 0.5)
        self.assertEqual(citation_recall(cited, ["doc-a", "doc-b"]), 0.5)

    def test_acl_leakage_rate_is_measurable(self):
        self.assertEqual(leakage_rate(["allowed", "forbidden"], ["forbidden"]), 0.5)
        self.assertEqual(leakage_rate([], ["forbidden"]), 0.0)

    def test_ndcg_rewards_correct_evidence_order(self):
        graded = {"primary": 3, "supporting": 1}

        self.assertEqual(ndcg_at_k(["primary", "supporting"], graded, 2), 1.0)
        self.assertLess(ndcg_at_k(["supporting", "primary"], graded, 2), 1.0)

    def test_fact_and_forbidden_fact_matching_normalizes_text(self):
        answer = "须在 4 个工作小时内联系；不能输出旧 API 密钥。"

        self.assertEqual(fact_coverage(answer, [["4个工作小时"], ["不能输出旧API密钥"]]), 1.0)
        self.assertEqual(forbidden_fact_rate(answer, ["旧API密钥", "内部底价"]), 0.5)

    def test_empty_relevance_contract_is_rejected(self):
        with self.assertRaises(ValueError):
            recall_at_k(["doc"], [], 5)
        with self.assertRaises(ValueError):
            citation_recall(["doc"], [])


if __name__ == "__main__":
    unittest.main()
