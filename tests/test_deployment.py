import tempfile
import unittest
from pathlib import Path

import yaml

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
        self.assertIn("langgraph-checkpoint-postgres==3.1.2", requirements)
        self.assertIn("psycopg[binary,pool]==3.3.2", requirements)
        self.assertIn("redis==8.1.0", requirements)
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
            "RAG_DATABASE_URL:?",
            "RAG_REDIS_URL:?",
            "RAG_STATE_BACKEND: postgres",
            "HF_HOME: /models",
        ):
            self.assertIn(control, compose)
        self.assertNotIn("CHANGEME", compose)
        self.assertNotIn("rag_state:/var/lib/rag", compose)

    def test_environment_example_matches_dual_backend_defaults(self):
        example = (ROOT / ".env.example").read_text(encoding="utf-8")

        for setting in (
            "RAG_STATE_BACKEND=sqlite",
            "RAG_DATABASE_URL=",
            "RAG_DB_POOL_MAX_SIZE=16",
            "RAG_REDIS_URL=",
            "RAG_CONVERSATION_LOCK_TTL_SECONDS=45",
            "RAG_MAX_CONCURRENT_REQUESTS=12",
        ):
            self.assertIn(setting, example)

    def test_integration_compose_pins_postgres_and_redis_images(self):
        compose = (ROOT / "deploy" / "docker-compose.integration.yml").read_text(encoding="utf-8")

        self.assertIn("postgres:17-alpine@sha256:", compose)
        self.assertIn("redis:7.4-alpine@sha256:", compose)
        self.assertIn("profiles: [integration]", compose)

    def test_kubernetes_baseline_is_three_replica_and_cross_zone(self):
        documents = list(
            yaml.safe_load_all((ROOT / "deploy" / "k8s" / "runtime.yaml").read_text(encoding="utf-8"))
        )
        deployment = next(item for item in documents if item and item.get("kind") == "Deployment")
        pdb = next(item for item in documents if item and item.get("kind") == "PodDisruptionBudget")
        hpa = next(item for item in documents if item and item.get("kind") == "HorizontalPodAutoscaler")

        self.assertEqual(deployment["spec"]["replicas"], 3)
        self.assertEqual(deployment["spec"]["strategy"]["rollingUpdate"]["maxUnavailable"], 0)
        self.assertEqual(
            deployment["spec"]["template"]["spec"]["topologySpreadConstraints"][0]["topologyKey"],
            "topology.kubernetes.io/zone",
        )
        container = deployment["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(container["args"][-1], "1")
        self.assertTrue(container["securityContext"]["readOnlyRootFilesystem"])
        self.assertEqual(pdb["spec"]["minAvailable"], 2)
        self.assertEqual(hpa["spec"]["minReplicas"], 3)
        self.assertEqual(hpa["spec"]["maxReplicas"], 9)

    def test_kubernetes_runs_two_independent_recovery_workers(self):
        documents = list(
            yaml.safe_load_all((ROOT / "deploy" / "k8s" / "runtime.yaml").read_text(encoding="utf-8"))
        )
        deployments = {
            item["metadata"]["name"]: item
            for item in documents
            if item and item.get("kind") == "Deployment"
        }
        worker = deployments["rag-recovery-worker"]
        container = worker["spec"]["template"]["spec"]["containers"][0]

        self.assertEqual(worker["spec"]["replicas"], 2)
        self.assertIn("rag_service.recovery_worker", container["args"])
        self.assertTrue(container["securityContext"]["readOnlyRootFilesystem"])
        self.assertIn("readinessProbe", container)

    def test_kubernetes_jobs_migrate_and_prune_shared_state(self):
        documents = list(
            yaml.safe_load_all((ROOT / "deploy" / "k8s" / "jobs.yaml").read_text(encoding="utf-8"))
        )
        job = next(item for item in documents if item and item.get("kind") == "Job")
        cron = next(item for item in documents if item and item.get("kind") == "CronJob")

        self.assertIn("schema", job["spec"]["template"]["spec"]["containers"][0]["args"])
        self.assertEqual(cron["spec"]["concurrencyPolicy"], "Forbid")
        self.assertIn("prune", cron["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]["args"])

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
