"""Production-facing composition package for the RAG service."""

from rag_service.settings import Settings, SettingsError, get_settings

__all__ = ["Settings", "SettingsError", "get_settings"]
