import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from rag_service.application import ApplicationRuntime, create_runtime
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

    def test_runtime_creation_closes_partial_resources_when_graph_build_fails(self):
        checkpoints = Mock()
        checkpoints.saver = Mock()
        conversations = Mock()
        coordination = Mock()

        with (
            patch("rag_service.application.create_checkpointer", return_value=checkpoints),
            patch(
                "rag_service.application.create_conversation_store",
                return_value=conversations,
            ),
            patch(
                "rag_service.application.create_coordination",
                return_value=(coordination, Mock()),
            ),
            patch("rag_service.application.create_graph", side_effect=RuntimeError("build failed")),
        ):
            with self.assertRaisesRegex(RuntimeError, "build failed"):
                create_runtime(settings=Settings())

        coordination.close.assert_called_once_with()
        conversations.close.assert_called_once_with()
        checkpoints.close.assert_called_once_with()

    def test_runtime_close_attempts_every_resource_when_one_close_fails(self):
        conversations = Mock()
        conversations.close.side_effect = RuntimeError("conversation close failed")
        coordination = Mock()
        checkpoints = Mock()
        runtime = ApplicationRuntime(
            graph=Mock(),
            checkpoints=checkpoints,
            conversations=conversations,
            coordination=coordination,
            settings=Settings(),
            resilience=Mock(),
            telemetry=Mock(),
        )

        with self.assertRaisesRegex(RuntimeError, "conversation close failed"):
            runtime.close()

        conversations.close.assert_called_once_with()
        coordination.close.assert_called_once_with()
        checkpoints.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
