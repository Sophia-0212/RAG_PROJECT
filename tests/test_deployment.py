import tempfile
import unittest
from pathlib import Path

from rag_service.migrations import migrate_local_state


ROOT = Path(__file__).resolve().parents[1]


class DeploymentContractTest(unittest.TestCase):
    def test_service_image_is_pinned_and_runs_as_non_root(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

        self.assertEqual(dockerfile.count("@sha256:"), 2)
        self.assertIn("USER 10001:10001", dockerfile)
        self.assertIn("LANGGRAPH_STRICT_MSGPACK=true", dockerfile)
        self.assertIn('"--workers", "1"', dockerfile)
        self.assertIn("https://download.pytorch.org/whl/cpu", dockerfile)
        self.assertIn("requirements.service.lock", dockerfile)
        self.assertIn('--no-deps "langchain-milvus==0.4.0"', dockerfile)
        self.assertNotIn("COPY .env", dockerfile)

    def test_service_dependency_set_excludes_ingestion_only_packages(self):
        requirements = (ROOT / "requirements.service.lock").read_text(encoding="utf-8")

        self.assertIn("torch==2.9.1", requirements)
        self.assertIn("sentence-transformers==6.0.0", requirements)
        self.assertNotIn("unstructured", requirements)
        self.assertNotIn("milvus-lite==", requirements)

    def test_build_context_excludes_local_secrets_and_state(self):
        ignored = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()

        self.assertIn(".env", ignored)
        self.assertIn(".rag-state", ignored)
        self.assertIn(".git", ignored)
        self.assertIn("test", ignored)

    def test_production_compose_has_security_and_required_inputs(self):
        compose = (ROOT / "deploy" / "docker-compose.yml").read_text(encoding="utf-8")

        for control in (
            "read_only: true",
            "cap_drop:",
            "no-new-privileges:true",
            "RAG_GATEWAY_SHARED_SECRET:?",
            "MILVUS_URI:?",
            "RAG_MODEL_CACHE_PATH:?",
            "HF_HOME: /models",
        ):
            self.assertIn(control, compose)
        self.assertNotIn("CHANGEME", compose)

    def test_langfuse_compose_contains_no_example_secret_defaults(self):
        compose = (ROOT / "langfuse" / "docker-compose.yml").read_text(encoding="utf-8")

        self.assertNotIn("CHANGEME", compose)
        for required in (
            "NEXTAUTH_SECRET:?",
            "ENCRYPTION_KEY:?",
            "CLICKHOUSE_PASSWORD:?",
            "REDIS_AUTH:?",
            "MINIO_ROOT_PASSWORD:?",
            "POSTGRES_PASSWORD:?",
        ):
            self.assertIn(required, compose)

    def test_local_state_migration_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "state" / "checkpoints.sqlite3")

            first = migrate_local_state(path)
            second = migrate_local_state(path)

            self.assertEqual(first, {"checkpoint": "ready", "conversation": "ready"})
            self.assertEqual(second, first)
            self.assertTrue(Path(path).is_file())


if __name__ == "__main__":
    unittest.main()
