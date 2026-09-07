import hashlib
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from evaluation.assets import validate_assets
from evaluation.schema import CATEGORIES, DatasetError, EvalCase, load_dataset


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET = PROJECT_ROOT / "evaluation" / "datasets" / "ad_crm_golden_small_v1.jsonl"
MANIFEST = PROJECT_ROOT / "evaluation" / "corpus" / "ad_crm_v1" / "manifest.json"


class EvaluationSchemaTest(unittest.TestCase):
    def test_versioned_golden_dataset_loads_with_governed_coverage(self):
        cases = load_dataset(DATASET)

        self.assertEqual(len(cases), 64)
        self.assertEqual({case.dataset_version for case in cases}, {"ad-crm-golden-small-v1.0.0"})
        self.assertEqual(Counter(case.category for case in cases), Counter({name: 8 for name in CATEGORIES}))
        self.assertEqual(Counter(case.split for case in cases), {"development": 16, "locked": 40, "security": 8})
        self.assertTrue(any(case.should_refuse for case in cases))
        self.assertTrue(any(case.history for case in cases))

    def test_corpus_and_dataset_assets_are_consistent(self):
        report = validate_assets(DATASET, MANIFEST)

        self.assertEqual(report.case_count, 64)
        self.assertEqual(report.snapshot_id, "ad-crm-snapshot-2026-09-01")
        self.assertGreaterEqual(report.evidence_refs_used, 30)

    def test_release_fingerprints_match_frozen_assets(self):
        release = json.loads((PROJECT_ROOT / "evaluation" / "dataset_release.json").read_text(encoding="utf-8"))

        for path_field, digest_field in (
            ("dataset_path", "dataset_sha256"),
            ("corpus_manifest_path", "corpus_manifest_sha256"),
        ):
            content = (PROJECT_ROOT / release[path_field]).read_bytes()
            self.assertEqual(hashlib.sha256(content).hexdigest(), release[digest_field])

    def test_dataset_contains_no_obvious_contact_identifiers(self):
        content = DATASET.read_text(encoding="utf-8")

        self.assertNotRegex(content, r"1[3-9]\d{9}")
        self.assertNotRegex(content, r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

    def test_answer_case_requires_evidence_and_identity(self):
        with self.assertRaisesRegex(DatasetError, "principal_ids"):
            EvalCase.from_mapping(
                {
                    "case_id": "missing-identity",
                    "dataset_version": "v1",
                    "split": "development",
                    "category": "single_fact",
                    "business_domain": "lead_management",
                    "risk_level": "low",
                    "tenant_id": "tenant-test",
                    "principal_ids": [],
                    "as_of": "2026-09-01T10:00:00+08:00",
                    "question": "question",
                    "expected_action": "answer",
                    "expected_route": "vectorstore",
                    "annotation": {
                        "method": "synthetic_sme",
                        "status": "adjudicated",
                        "guideline_version": "1.0",
                        "annotator_roles": ["crm_sme"],
                    },
                }
            )

    def test_duplicate_ids_are_rejected(self):
        case = DATASET.read_text(encoding="utf-8").splitlines()[0]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dataset.jsonl"
            path.write_text(f"{case}\n{case}\n", encoding="utf-8")
            with self.assertRaisesRegex(DatasetError, "Duplicate case_id"):
                load_dataset(path)


if __name__ == "__main__":
    unittest.main()
