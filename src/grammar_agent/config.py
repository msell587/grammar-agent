"""Runtime settings, read from the environment (and ``.env``) with CLI overrides."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

PROVIDERS = ("gemini", "groq", "ollama", "mock")
LEVELS = ("beginner", "intermediate", "advanced")

DEFAULT_MODELS = {
    "gemini": "gemini-2.5-flash",
    "groq": "llama-3.3-70b-versatile",
    "ollama": "llama3.1:8b",
    "mock": "mock",
}


class ConfigError(ValueError):
    """Raised for invalid or missing configuration (e.g. no API key)."""


@dataclass(frozen=True)
class Settings:
    provider: str = "gemini"
    model: str = DEFAULT_MODELS["gemini"]
    level: str = "intermediate"

    # Guardrails
    max_retries: int = 2  # extra attempts after a malformed response
    max_length_ratio: float = 0.30  # reject if |len diff| / len(original) exceeds this...
    min_length_slack: int = 12  # ...AND the absolute difference exceeds this many characters

    # Rate limiting
    request_delay: float = 6.5  # seconds between uncached requests (free tier ~10 RPM)
    backoff_initial: float = 2.0
    backoff_max: float = 60.0
    rate_limit_attempts: int = 5
    timeout: float = 60.0

    # Cache
    cache_path: Path = Path(".grammar_agent_cache.sqlite")
    use_cache: bool = True

    # Provider credentials / endpoints (never logged)
    gemini_api_key: str | None = None
    groq_api_key: str | None = None
    ollama_host: str = "http://localhost:11434"

    # Offline demo: a JSON file of scripted replies for the mock provider
    mock_script: Path | None = None

    def with_overrides(self, **overrides: Any) -> Settings:
        """Return a copy with every non-None override applied and validated."""
        clean = {k: v for k, v in overrides.items() if v is not None}
        if "provider" in clean and "model" not in clean:
            clean["model"] = DEFAULT_MODELS[clean["provider"]]
        return replace(self, **clean).validated()

    def validated(self) -> Settings:
        if self.provider not in PROVIDERS:
            raise ConfigError(f"Unknown provider {self.provider!r}; choose from {PROVIDERS}.")
        if self.level not in LEVELS:
            raise ConfigError(f"Unknown level {self.level!r}; choose from {LEVELS}.")
        if self.max_retries < 0 or self.request_delay < 0 or self.max_length_ratio <= 0:
            raise ConfigError("max_retries, request_delay and max_length_ratio must be positive.")
        return self


def _float(env: Mapping[str, str], key: str, default: float) -> float:
    raw = env.get(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{key} must be a number, got {raw!r}.") from exc


def load_settings(env: Mapping[str, str] | None = None, *, dotenv: bool = True) -> Settings:
    """Build settings from ``env`` (defaults to ``os.environ`` after loading ``.env``)."""
    if env is None:
        if dotenv:
            load_dotenv()
        env = os.environ
    provider = env.get("GRAMMAR_AGENT_PROVIDER", "gemini").strip().lower() or "gemini"
    model_var = {"gemini": "GEMINI_MODEL", "groq": "GROQ_MODEL", "ollama": "OLLAMA_MODEL"}
    model = env.get(model_var.get(provider, ""), "") or DEFAULT_MODELS.get(provider, "")
    return Settings(
        provider=provider,
        model=model,
        level=env.get("GRAMMAR_AGENT_LEVEL", "intermediate").strip().lower() or "intermediate",
        request_delay=_float(env, "GRAMMAR_AGENT_REQUEST_DELAY", Settings.request_delay),
        max_length_ratio=_float(env, "GRAMMAR_AGENT_MAX_LENGTH_RATIO", Settings.max_length_ratio),
        cache_path=Path(env.get("GRAMMAR_AGENT_CACHE", "") or Settings.cache_path),
        gemini_api_key=env.get("GEMINI_API_KEY") or None,
        groq_api_key=env.get("GROQ_API_KEY") or None,
        ollama_host=env.get("OLLAMA_HOST", "") or Settings.ollama_host,
        mock_script=Path(env["GRAMMAR_AGENT_MOCK_SCRIPT"])
        if env.get("GRAMMAR_AGENT_MOCK_SCRIPT")
        else None,
    ).validated()
