from collections.abc import Callable
from pathlib import Path

import pytest

from grammar_agent.cache import ResponseCache
from grammar_agent.checker import Checker
from grammar_agent.config import Settings
from grammar_agent.llm import LLMError, MockClient, RateLimitError
from grammar_agent.models import Sentence, Status
from grammar_agent.ratelimit import RateLimiter

S = "I has a cat."


def no_sleep_limiter() -> RateLimiter:
    return RateLimiter(attempts=3, sleep=lambda _: None)


def sentence(text: str = S) -> Sentence:
    return Sentence(1, text, 0, len(text))


def test_valid_reply_becomes_changes(settings: Settings, make_reply: Callable[..., str]) -> None:
    client = MockClient({S: make_reply(S, "I have a cat.", [("has", "have", "grammar")])})
    result = Checker(client, settings).check_sentence(sentence())
    assert result.status is Status.CHANGES_PROPOSED
    assert [c.id for c in result.changes] == ["1.1"]


def test_retries_malformed_then_succeeds(
    settings: Settings, make_reply: Callable[..., str]
) -> None:
    good = make_reply(S, S, [])
    client = MockClient({S: ["not json", '{"original": 1}', good]})
    checker = Checker(client, settings)
    result = checker.check_sentence(sentence())
    assert result.status is Status.NO_CHANGES
    assert checker.llm_calls == 3


def test_gives_up_after_two_retries(settings: Settings) -> None:
    client = MockClient({S: "still not json"})
    checker = Checker(client, settings)
    result = checker.check_sentence(sentence())
    assert result.status is Status.NEEDS_REVIEW
    assert "malformed JSON 3 times" in result.review_reasons[0]
    assert result.corrected == S
    assert checker.llm_calls == 3


def test_guardrail_failure_flags_but_does_not_crash(
    settings: Settings, make_reply: Callable[..., str]
) -> None:
    client = MockClient(
        {S: make_reply(S, "I own a dog.", [("has a cat", "own a dog", "other")], False)}
    )
    result = Checker(client, settings).check_sentence(sentence())
    assert result.status is Status.NEEDS_REVIEW
    assert result.review_reasons


def test_persistent_rate_limit_flags_sentence(settings: Settings) -> None:
    client = MockClient({S: RateLimitError("429")})
    result = Checker(client, settings, limiter=no_sleep_limiter()).check_sentence(sentence())
    assert result.status is Status.NEEDS_REVIEW
    assert "rate-limited, overloaded or timed out" in result.review_reasons[0]


def test_non_fatal_error_flags_sentence(settings: Settings) -> None:
    client = MockClient({S: LLMError("safety block")})
    result = Checker(client, settings).check_sentence(sentence())
    assert result.status is Status.NEEDS_REVIEW


def test_fatal_error_stops_the_run(settings: Settings) -> None:
    client = MockClient({S: LLMError("bad key", fatal=True)})
    with pytest.raises(LLMError):
        Checker(client, settings).check_sentence(sentence())


def test_cache_makes_rerun_free(
    tmp_path: Path, settings: Settings, make_reply: Callable[..., str]
) -> None:
    script = {S: make_reply(S, "I have a cat.", [("has", "have", "grammar")])}
    with ResponseCache(tmp_path / "c.sqlite") as cache:
        first = MockClient(script)
        Checker(first, settings, cache).check_text(S + " Fine.")
        assert len(first.calls) == 2
        second = MockClient(script)
        results = Checker(second, settings, cache).check_text(S + " Fine.")
        assert second.calls == []
        assert results[0].changes[0].replacement == "have"


def test_malformed_replies_are_not_cached(tmp_path: Path, settings: Settings) -> None:
    with ResponseCache(tmp_path / "c.sqlite") as cache:
        Checker(MockClient({S: "junk"}), settings, cache).check_sentence(sentence())
        assert len(cache) == 0


def test_level_changes_cache_key(
    tmp_path: Path, settings: Settings, make_reply: Callable[..., str]
) -> None:
    with ResponseCache(tmp_path / "c.sqlite") as cache:
        Checker(MockClient(), settings, cache).check_sentence(sentence())
        client = MockClient()
        Checker(client, settings.with_overrides(level="beginner"), cache).check_sentence(sentence())
        assert client.calls == [S]


def test_check_text_reports_progress(settings: Settings) -> None:
    seen: list[int] = []
    Checker(MockClient(), settings).check_text("One. Two. Three.", lambda r, n: seen.append(n))
    assert seen == [3, 3, 3]
