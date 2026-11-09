import json
from typing import Any

import pytest

from grammar_agent.parsing import ParseError, extract_json_object, parse_response

GOOD: dict[str, Any] = {
    "original": "I has a cat.",
    "corrected": "I have a cat.",
    "meaning_preserved": True,
    "changes": [
        {
            "original_span": "has",
            "replacement": "have",
            "type": "grammar",
            "explanation": "Use 'have' with 'I'.",
        }
    ],
}


def test_parses_plain_json() -> None:
    result = parse_response(json.dumps(GOOD))
    assert result.corrected == "I have a cat."
    assert result.changes[0].type == "grammar"


def test_parses_fenced_json_and_surrounding_prose() -> None:
    fenced = "```json\n" + json.dumps(GOOD) + "\n```"
    assert parse_response(fenced).corrected == "I have a cat."
    chatty = "Sure! Here you go:\n" + json.dumps(GOOD) + "\nHope that helps."
    assert parse_response(chatty).corrected == "I have a cat."


@pytest.mark.parametrize(
    "text",
    [
        "",
        "no json here",
        "{not valid json}",
        "[1, 2, 3]",
        '{"original": "x"',
    ],
)
def test_malformed_raises(text: str) -> None:
    with pytest.raises(ParseError):
        parse_response(text)


@pytest.mark.parametrize("missing", ["original", "corrected", "meaning_preserved", "changes"])
def test_missing_field_raises(missing: str) -> None:
    data = {k: v for k, v in GOOD.items() if k != missing}
    with pytest.raises(ParseError):
        parse_response(json.dumps(data))


def test_wrong_types_raise() -> None:
    with pytest.raises(ParseError):
        parse_response(json.dumps({**GOOD, "changes": "none"}))
    with pytest.raises(ParseError):
        parse_response(json.dumps({**GOOD, "changes": [{"original_span": "has"}]}))
    with pytest.raises(ParseError):
        parse_response(json.dumps({**GOOD, "meaning_preserved": "maybe"}))


def test_lenient_on_bool_strings_and_unknown_type() -> None:
    change = {**GOOD["changes"][0], "type": "Word Choice"}
    data = {**GOOD, "meaning_preserved": "true", "changes": [change]}
    result = parse_response(json.dumps(data))
    assert result.meaning_preserved is True
    assert result.changes[0].type == "other"


def test_extract_json_object_rejects_empty() -> None:
    with pytest.raises(ParseError):
        extract_json_object("   ")


def test_category_parsed_and_normalized() -> None:
    change = {**GOOD["changes"][0], "category": "Subject-Verb Agreement"}
    result = parse_response(json.dumps({**GOOD, "changes": [change]}))
    assert result.changes[0].category == "subject_verb_agreement"


def test_missing_or_unknown_category_falls_back_without_retry() -> None:
    spelling = {**GOOD["changes"][0], "type": "spelling"}
    spelling.pop("category", None)
    unknown = {**GOOD["changes"][0], "category": "vibes"}
    result = parse_response(json.dumps({**GOOD, "changes": [spelling, unknown]}))
    assert [c.category for c in result.changes] == ["spelling", "other"]
