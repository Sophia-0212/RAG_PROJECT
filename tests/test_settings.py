import unittest

from rag_service.settings import Settings, SettingsError


class SettingsTest(unittest.TestCase):
    def test_defaults_are_typed(self):
        settings = Settings.from_mapping({})

        self.assertEqual(settings.retrieval_top_k, 16)
        self.assertEqual(settings.rerank_top_n, 4)
        self.assertEqual(settings.embedding_dimension, 512)
        self.assertTrue(settings.hf_hub_offline)
        self.assertEqual(settings.max_steps, 16)
        self.assertEqual(settings.conversation_ttl_seconds, 86400)
        self.assertEqual(settings.state_backend, "sqlite")
        self.assertEqual(settings.max_concurrent_requests, 12)

    def test_environment_overrides_are_parsed(self):
        settings = Settings.from_mapping(
            {
                "RAG_RETRIEVAL_TOP_K": "24",
                "RAG_RERANK_TOP_N": "6",
                "RAG_RETRIEVAL_SCORE_THRESHOLD": "0.25",
                "RAG_FUSION_MODE": "weighted",
                "RAG_DENSE_WEIGHT": "0.7",
                "RAG_SPARSE_WEIGHT": "0.3",
                "HF_HUB_OFFLINE": "false",
                "RAG_MAX_GENERATION_ATTEMPTS": "5",
                "RAG_REQUEST_TIMEOUT_SECONDS": "12.5",
                "RAG_STATE_BACKEND": "postgres",
                "RAG_DATABASE_URL": "postgresql://rag:secret@db.internal/rag",
                "RAG_REDIS_URL": "rediss://redis.internal:6379/0",
                "RAG_DB_POOL_MAX_SIZE": "24",
                "RAG_RECOVERY_ENABLED": "true",
                "RAG_RECOVERY_MAX_ATTEMPTS": "4",
            }
        )

        self.assertEqual(settings.retrieval_top_k, 24)
        self.assertEqual(settings.rerank_top_n, 6)
        self.assertEqual(settings.retrieval_score_threshold, 0.25)
        self.assertFalse(settings.hf_hub_offline)
        self.assertEqual(settings.fusion_mode, "weighted")
        self.assertEqual(settings.dense_weight, 0.7)
        self.assertEqual(settings.max_generation_attempts, 5)
        self.assertEqual(settings.request_timeout_seconds, 12.5)
        self.assertEqual(settings.state_backend, "postgres")
        self.assertEqual(settings.db_pool_max_size, 24)
        self.assertTrue(settings.recovery_enabled)
        self.assertEqual(settings.recovery_max_attempts, 4)

    def test_invalid_numeric_configuration_fails_fast(self):
        with self.assertRaises(SettingsError):
            Settings.from_mapping({"RAG_RETRIEVAL_TOP_K": "0"})
        with self.assertRaises(SettingsError):
            Settings.from_mapping({"RAG_RETRIEVAL_SCORE_THRESHOLD": "1.5"})
        with self.assertRaises(SettingsError):
            Settings.from_mapping({"RAG_FUSION_MODE": "unknown"})
        with self.assertRaises(SettingsError):
            Settings.from_mapping({"RAG_DENSE_WEIGHT": "0", "RAG_SPARSE_WEIGHT": "0"})
        with self.assertRaises(SettingsError):
            Settings.from_mapping({"RAG_STATE_BACKEND": "unknown"})
        with self.assertRaises(SettingsError):
            Settings.from_mapping({"RAG_DB_POOL_MIN_SIZE": "5", "RAG_DB_POOL_MAX_SIZE": "4"})
        with self.assertRaises(SettingsError):
            Settings.from_mapping(
                {"RAG_REQUEST_TIMEOUT_SECONDS": "30", "RAG_CONVERSATION_LOCK_TTL_SECONDS": "30"}
            )
        with self.assertRaises(SettingsError):
            Settings.from_mapping({"RAG_RECOVERY_ENABLED": "true"})
        with self.assertRaises(SettingsError):
            Settings.from_mapping({"RAG_RUN_LEASE_SECONDS": "10", "RAG_RUN_HEARTBEAT_SECONDS": "10"})
        with self.assertRaises(SettingsError):
            Settings.from_mapping(
                {
                    "RAG_STATE_BACKEND": "postgres",
                    "RAG_RECOVERY_ENABLED": "true",
                    "RAG_RUN_LEASE_SECONDS": "20",
                    "RAG_REQUEST_TIMEOUT_SECONDS": "30",
                }
            )

    def test_production_recovery_requires_https_reauthorization_contract(self):
        settings = Settings(
            environment="production",
            openai_api_key="configured",
            milvus_uri="https://milvus.internal:19530",
            state_backend="postgres",
            database_url="postgresql://rag:secret@postgres.internal/rag",
            redis_url="rediss://redis.internal:6379/0",
            recovery_enabled=True,
        )

        with self.assertRaisesRegex(SettingsError, "RAG_RECOVERY_AUTHORIZATION_URL"):
            settings.validate_service_startup(identity_provider_configured=True)

    def test_runtime_credentials_are_validated_at_use_boundary(self):
        settings = Settings.from_mapping({})

        with self.assertRaisesRegex(SettingsError, "OPENAI_API_KEY"):
            settings.require_llm()
        with self.assertRaisesRegex(SettingsError, "TAVILY_API_KEY"):
            settings.require_web_search()

    def test_production_profile_rejects_unsafe_defaults(self):
        settings = Settings(environment="production")

        with self.assertRaisesRegex(SettingsError, "unsafe production configuration"):
            settings.validate_service_startup(identity_provider_configured=False)

    def test_production_profile_accepts_explicit_secure_boundaries(self):
        settings = Settings(
            environment="production",
            openai_api_key="configured",
            milvus_uri="https://milvus.internal:19530",
            state_backend="postgres",
            database_url="postgresql://rag:secret@postgres.internal/rag",
            redis_url="rediss://redis.internal:6379/0",
        )

        settings.validate_service_startup(identity_provider_configured=True)

    def test_production_profile_rejects_weak_gateway_secret(self):
        settings = Settings(
            environment="production",
            openai_api_key="configured",
            milvus_uri="https://milvus.internal:19530",
            checkpoint_path="/var/lib/rag/checkpoints.sqlite3",
            gateway_shared_secret="too-short",
        )

        with self.assertRaisesRegex(SettingsError, "at least 32"):
            settings.validate_service_startup(identity_provider_configured=True)

    def test_production_profile_rejects_invalid_dependency_schemes(self):
        settings = Settings(
            environment="production",
            openai_api_key="configured",
            milvus_uri="https://milvus.internal:19530",
            state_backend="postgres",
            database_url="sqlite:///var/lib/rag/state.db",
            redis_url="http://redis.internal:6379/0",
        )

        with self.assertRaisesRegex(SettingsError, "postgresql://"):
            settings.validate_service_startup(identity_provider_configured=True)
        with self.assertRaisesRegex(SettingsError, "rediss://"):
            settings.validate_service_startup(identity_provider_configured=True)

    def test_secret_values_are_not_exposed_by_repr(self):
        settings = Settings(
            openai_api_key="llm-secret",
            database_url="postgresql://rag:db-secret@postgres.internal/rag",
            redis_url="rediss://:redis-secret@redis.internal:6379/0",
            gateway_shared_secret="gateway-secret-value",
            recovery_authorization_token="recovery-secret-value",
        )

        rendered = repr(settings)

        for secret in (
            "llm-secret",
            "db-secret",
            "redis-secret",
            "gateway-secret-value",
            "recovery-secret-value",
        ):
            self.assertNotIn(secret, rendered)


if __name__ == "__main__":
    unittest.main()
