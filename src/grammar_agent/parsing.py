"""Defensive parsing of the model's reply into typed data.

Models sometimes wrap JSON in Markdown fences, add a sentence of prose, or drop
a field. This module accepts the first form gracefully and turns everything
else into a ``ParseError`` so the checker can retry.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from grammar_agent.models import CHANGE_TYPES, MISTAKE_CATEGORIES


class ParseError(ValueError):
    """The reply was not a JSON object matching the expected schema."""


@dataclass(frozen=True)
class RawChange:
    original_span: str
    replacement: str
    type: str
    explanation: str
    category: str = "other"


@dataclass(frozen=True)
class RawResult:
    original: str
    corrected: str
    meaning_preserved: bool
    changes: list[RawChange]


_FENCE = re.compile(r"^```[a-zA-Z]*\s*\n?|\n?```\s*$")


def extract_json_object(text: str) -> dict[str, Any]:
    """Pull the outermost JSON object out of ``text``."""
    cleaned = _FENCE.sub("", text.strip())
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ParseError("no JSON object found in the reply")
    try:
        value = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ParseError(f"invalid JSON: {exc.msg} at position {exc.pos}") from exc
    if not isinstance(value, dict):
        raise ParseError("top-level JSON value is not an object")
    return value


def _str(data: dict[str, Any], key: str, where: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise ParseError(f"{where}{key!r} must be a string")
    return value


def _bool(data: dict[str, Any], key: str) -> bool:
    value = data.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    raise ParseError(f"{key!r} must be a boolean")


def _category(item: dict[str, Any], change_type: str) -> str:
    """Normalize the optional category. A missing or unknown one is not worth a retry."""
    value = item.get("category")
    if isinstance(value, str):
        slug = re.sub(r"[\s\-]+", "_", value.strip().lower())
        if slug in MISTAKE_CATEGORIES:
            return slug
    return change_type if change_type in MISTAKE_CATEGORIES else "other"


def parse_response(text: str) -> RawResult:
    """Parse and validate one model reply. Raises ParseError if it is unusable."""
    data = extract_json_object(text)
    changes_raw = data.get("changes")
    if not isinstance(changes_raw, list):
        raise ParseError("'changes' must be a list")
    changes: list[RawChange] = []
    for i, item in enumerate(changes_raw, start=1):
        if not isinstance(item, dict):
            raise ParseError(f"change {i} is not an object")
        where = f"change {i}: "
        kind = _str(item, "type", where).strip().lower()
        kind = kind if kind in CHANGE_TYPES else "other"
        changes.append(
            RawChange(
                original_span=_str(item, "original_span", where),
                replacement=_str(item, "replacement", where),
                # An unknown label is not worth a retry; keep the change, file it as "other".
                type=kind,
                explanation=_str(item, "explanation", where).strip(),
                category=_category(item, kind),
            )
        )
    return RawResult(
        original=_str(data, "original", ""),
        corrected=_str(data, "corrected", ""),
        meaning_preserved=_bool(data, "meaning_preserved"),
        changes=changes,
    )
