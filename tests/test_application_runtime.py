import tempfile
import unittest
from pathlib import Path

from rag_service.application import create_runtime
from rag_service.settings import Settings


class ApplicationRuntimeTest(unittest.TestCase):
    def test_local_runtime_composes_checkpoint_resilience_and_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = create_runtime(
                settings=Settings(checkpoint_path=str(Path(directory) / "runtime.sqlite3"))
            )
            try:
                self.assertTrue(runtime.conversations.ping())
                self.assertIn("retrieval", runtime.resilience.dependency_guards)
                self.assertIn(b"rag_requests_total", runtime.telemetry.metrics())
            finally:
                runtime.close()


if __name__ == "__main__":
    unittest.main()
