import json
from collections.abc import Callable

import pytest

from grammar_agent.config import Settings


def reply(
    original: str, corrected: str, changes: list[tuple[str, str, str]], meaning: bool = True
) -> str:
    """Build a model reply. ``changes`` is a list of (span, replacement, type)."""
    return json.dumps(
        {
            "original": original,
            "corrected": corrected,
            "meaning_preserved": meaning,
            "changes": [
                {"original_span": a, "replacement": b, "type": t, "explanation": f"Fix {a}."}
                for a, b, t in changes
            ],
        }
    )


@pytest.fixture
def make_reply() -> Callable[..., str]:
    return reply


@pytest.fixture
def settings() -> Settings:
    return Settings().with_overrides(provider="mock", request_delay=0.0)
