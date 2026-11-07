"""Google Gemini (free tier via Google AI Studio) over plain REST."""

from __future__ import annotations

import copy
from typing import Any

import httpx

from grammar_agent.llm.base import LLMError
from grammar_agent.llm.http import post_json
from grammar_agent.prompts import RESPONSE_SCHEMA

API_ROOT = "https://generativelanguage.googleapis.com/v1beta"


def _to_gemini_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Gemini's ``responseSchema`` is an OpenAPI subset that uses upper-case type names."""
    out = copy.deepcopy(schema)

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("type"), str):
                node["type"] = node["type"].upper()
            for value in node.values():
                walk(value)

    walk(out)
    return out


class GeminiClient:
    def __init__(self, api_key: str, model: str, timeout: float = 60.0) -> None:
        if not api_key:
            raise LLMError("GEMINI_API_KEY is not set. Add it to your .env file.", fatal=True)
        self._api_key = api_key
        self._model = model
        self._http = httpx.Client(timeout=timeout)

    @property
    def model_id(self) -> str:
        return f"gemini:{self._model}"

    def complete(self, system: str, user: str) -> str:
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseSchema": _to_gemini_schema(RESPONSE_SCHEMA),
            },
        }
        data = post_json(
            self._http,
            f"{API_ROOT}/models/{self._model}:generateContent",
            payload,
            {"x-goog-api-key": self._api_key},  # header, so the key never appears in URLs/logs
            "Gemini",
        )
        try:
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(str(p.get("text", "")) for p in parts)
        except (KeyError, IndexError, TypeError) as exc:
            reason = data.get("promptFeedback") if isinstance(data, dict) else None
            raise LLMError(f"Gemini returned no candidate text ({reason})") from exc
