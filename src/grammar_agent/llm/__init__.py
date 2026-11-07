"""LLM provider implementations and a factory that picks one from settings."""

from __future__ import annotations

from grammar_agent.config import Settings
from grammar_agent.llm.base import LLMClient, LLMError, RateLimitError
from grammar_agent.llm.mock import MockClient, load_script

__all__ = ["LLMClient", "LLMError", "MockClient", "RateLimitError", "make_client"]


def make_client(settings: Settings) -> LLMClient:
    """Build the client named by ``settings.provider``."""
    if settings.provider == "gemini":
        from grammar_agent.llm.gemini import GeminiClient

        return GeminiClient(settings.gemini_api_key or "", settings.model, settings.timeout)
    if settings.provider == "groq":
        from grammar_agent.llm.groq import GroqClient

        return GroqClient(settings.groq_api_key or "", settings.model, settings.timeout)
    if settings.provider == "ollama":
        from grammar_agent.llm.ollama import OllamaClient

        return OllamaClient(settings.ollama_host, settings.model)
    if settings.provider == "mock":
        script = load_script(settings.mock_script) if settings.mock_script else None
        return MockClient(script, model=settings.model)
    raise LLMError(f"Unknown provider {settings.provider!r}")
