"""Ollama, for fully local and offline use (no key, nothing leaves your machine)."""

from __future__ import annotations

from typing import Any

import httpx

from grammar_agent.llm.base import LLMError
from grammar_agent.llm.http import post_json
from grammar_agent.prompts import RESPONSE_SCHEMA


class OllamaClient:
    def __init__(self, host: str, model: str, timeout: float = 120.0) -> None:
        self._host = host.rstrip("/")
        self._model = model
        self._http = httpx.Client(timeout=timeout)

    @property
    def model_id(self) -> str:
        return f"ollama:{self._model}"

    def complete(self, system: str, user: str, schema: dict[str, Any] | None = None) -> str:
        payload = {
            "model": self._model,
            "stream": False,
            "format": schema or RESPONSE_SCHEMA,  # structured outputs (Ollama >= 0.5)
            "options": {"temperature": 0},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            data = post_json(self._http, f"{self._host}/api/chat", payload, {}, "Ollama")
        except LLMError as exc:
            raise LLMError(
                f"{exc}. Is Ollama running (`ollama serve`) and is the model pulled "
                f"(`ollama pull {self._model}`)?"
            ) from exc
        try:
            return str(data["message"]["content"])
        except (KeyError, TypeError) as exc:
            raise LLMError("Ollama returned an unexpected response shape") from exc
