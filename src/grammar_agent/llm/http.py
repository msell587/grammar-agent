"""Shared HTTP helper so each provider only describes its request and response shape."""

from __future__ import annotations

from typing import Any

import httpx

from grammar_agent.llm.base import LLMError, RateLimitError, retry_after_seconds

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
FATAL_STATUS = {400, 401, 403, 404}


def post_json(
    client: httpx.Client, url: str, payload: dict[str, Any], headers: dict[str, str], provider: str
) -> Any:
    try:
        response = client.post(url, json=payload, headers=headers)
    except httpx.TimeoutException as exc:
        raise RateLimitError(f"{provider} request timed out") from exc
    except httpx.HTTPError as exc:
        raise LLMError(f"Could not reach {provider}: {exc}", fatal=True) from exc

    if response.status_code in RETRYABLE_STATUS:
        raise RateLimitError(
            f"{provider} returned HTTP {response.status_code}",
            retry_after=retry_after_seconds(response.headers.get("retry-after")),
        )
    if response.status_code >= 400:
        # The body explains the problem (e.g. invalid key). It never echoes the key itself.
        raise LLMError(
            f"{provider} returned HTTP {response.status_code}: {response.text[:300]}",
            fatal=response.status_code in FATAL_STATUS,
        )
    try:
        return response.json()
    except ValueError as exc:
        raise LLMError(f"{provider} returned a non-JSON HTTP body") from exc
