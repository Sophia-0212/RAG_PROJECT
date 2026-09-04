"""Backward-compatible access to the typed runtime settings.

New code should import ``get_settings`` from ``rag_service.settings`` directly.
The module-level aliases remain lazy so importing this module has no side effects.
"""

from rag_service.settings import Settings, SettingsError, get_settings, reset_settings_cache

_ALIASES = {
    "OPENAI_API_KEY": "openai_api_key",
    "DEEPSEEK_API_KEY": "deepseek_api_key",
    "TAVILY_API_KEY": "tavily_api_key",
    "LANGFUSE_SECRET_KEY": "langfuse_secret_key",
    "LANGFUSE_PUBLIC_KEY": "langfuse_public_key",
    "LANGFUSE_BASE_URL": "langfuse_base_url",
    "MILVUS_URI": "milvus_uri",
    "COLLECTION_NAME": "collection_name",
}


def __getattr__(name: str):
    attribute = _ALIASES.get(name)
    if attribute is None:
        raise AttributeError(name)
    return getattr(get_settings(), attribute)


__all__ = ["Settings", "SettingsError", "get_settings", "reset_settings_cache", *_ALIASES]
