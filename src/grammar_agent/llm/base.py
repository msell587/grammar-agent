"""The provider-neutral LLM interface."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


class LLMError(RuntimeError):
    """A provider failure that retrying the same request will not fix.

    ``fatal`` marks errors that will affect every sentence (bad API key, unknown
    model, provider unreachable). The checker stops the run for those instead of
    flagging every sentence one by one.
    """

    def __init__(self, message: str, *, fatal: bool = False) -> None:
        super().__init__(message)
        self.fatal = fatal


class RateLimitError(LLMError):
    """The provider asked us to slow down (HTTP 429) or is temporarily overloaded."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


@runtime_checkable
class LLMClient(Protocol):
    """Anything that can turn a system prompt plus a user prompt into raw text.

    Implementations return the model's text unparsed; parsing and validation
    live in :mod:`grammar_agent.parsing` so every provider is treated the same.
    """

    @property
    def model_id(self) -> str:
        """A stable identifier such as ``"gemini:gemini-3.5-flash"`` (used in cache keys)."""
        ...

    def complete(self, system: str, user: str, schema: dict[str, Any] | None = None) -> str:
        """Return the model's raw reply. Raise RateLimitError or LLMError on failure.

        ``schema`` is the JSON schema the reply must follow. It defaults to the grammar
        check's ``RESPONSE_SCHEMA``; other tools built on grammar-agent can pass their own.
        Providers that enforce schemas while generating (Gemini, Ollama) use it; the rest
        only promise JSON, so callers must still validate the reply.
        """
        ...


def retry_after_seconds(value: str | None) -> float | None:
    """Parse an HTTP ``Retry-After`` header given in seconds."""
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None
