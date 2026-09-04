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

    def test_invalid_numeric_configuration_fails_fast(self):
        with self.assertRaises(SettingsError):
            Settings.from_mapping({"RAG_RETRIEVAL_TOP_K": "0"})
        with self.assertRaises(SettingsError):
            Settings.from_mapping({"RAG_RETRIEVAL_SCORE_THRESHOLD": "1.5"})
        with self.assertRaises(SettingsError):
            Settings.from_mapping({"RAG_FUSION_MODE": "unknown"})
        with self.assertRaises(SettingsError):
            Settings.from_mapping({"RAG_DENSE_WEIGHT": "0", "RAG_SPARSE_WEIGHT": "0"})

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
            checkpoint_path="/var/lib/rag/checkpoints.sqlite3",
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


if __name__ == "__main__":
    unittest.main()
