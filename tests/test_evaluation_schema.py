import tempfile
import unittest
from pathlib import Path

from evaluation.schema import DatasetError, EvalCase, load_dataset


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class EvaluationSchemaTest(unittest.TestCase):
    def test_versioned_crm_smoke_dataset_loads(self):
        cases = load_dataset(PROJECT_ROOT / "evaluation" / "datasets" / "crm_smoke_v1.jsonl")

        self.assertEqual(len(cases), 5)
        self.assertEqual({case.dataset_version for case in cases}, {"crm-smoke-v1"})
        self.assertTrue(any(case.should_refuse for case in cases))

    def test_vector_case_requires_expected_sources(self):
        with self.assertRaisesRegex(DatasetError, "expected_source_ids"):
            EvalCase.from_mapping(
                {
                    "case_id": "missing-source",
                    "dataset_version": "v1",
                    "question": "question",
                }
            )

    def test_duplicate_ids_are_rejected(self):
        content = (
            '{"case_id":"same","dataset_version":"v1","question":"q1",'
            '"expected_source_ids":["a"]}\n'
            '{"case_id":"same","dataset_version":"v1","question":"q2",'
            '"expected_source_ids":["b"]}\n'
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "dataset.jsonl"
            path.write_text(content, encoding="utf-8")
            with self.assertRaisesRegex(DatasetError, "Duplicate case_id"):
                load_dataset(path)


if __name__ == "__main__":
    unittest.main()
