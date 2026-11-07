"""Groq free tier through its OpenAI-compatible chat completions endpoint."""

from __future__ import annotations

import httpx

from grammar_agent.llm.base import LLMError
from grammar_agent.llm.http import post_json

API_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqClient:
    def __init__(self, api_key: str, model: str, timeout: float = 60.0) -> None:
        if not api_key:
            raise LLMError("GROQ_API_KEY is not set. Add it to your .env file.")
        self._api_key = api_key
        self._model = model
        self._http = httpx.Client(timeout=timeout)

    @property
    def model_id(self) -> str:
        return f"groq:{self._model}"

    def complete(self, system: str, user: str) -> str:
        payload = {
            "model": self._model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        data = post_json(
            self._http, API_URL, payload, {"Authorization": f"Bearer {self._api_key}"}, "Groq"
        )
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("Groq returned an unexpected response shape") from exc
