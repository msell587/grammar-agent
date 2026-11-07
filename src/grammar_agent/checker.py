"""The pipeline for one sentence: cache -> LLM -> parse (with retries) -> guardrails."""

from __future__ import annotations

import logging
from collections.abc import Callable

from grammar_agent.cache import ResponseCache, cache_key
from grammar_agent.config import Settings
from grammar_agent.guardrails import GuardrailConfig, run_guardrails
from grammar_agent.llm.base import LLMClient, LLMError, RateLimitError
from grammar_agent.models import Sentence, SentenceResult, Status
from grammar_agent.parsing import ParseError, RawResult, parse_response
from grammar_agent.prompts import PROMPT_VERSION, system_prompt, user_prompt
from grammar_agent.ratelimit import RateLimiter
from grammar_agent.splitter import split_sentences

log = logging.getLogger(__name__)

ProgressFn = Callable[[SentenceResult, int], None]


def _retry_prompt(sentence: str, error: str) -> str:
    return (
        f"{user_prompt(sentence)}\n\nYour previous reply could not be used ({error}). "
        "Reply again with only one JSON object that matches the schema."
    )


class Checker:
    def __init__(
        self,
        client: LLMClient,
        settings: Settings,
        cache: ResponseCache | None = None,
        limiter: RateLimiter | None = None,
    ) -> None:
        self.client = client
        self.settings = settings
        self.cache = cache
        self.limiter = limiter or RateLimiter(
            delay=settings.request_delay,
            backoff_initial=settings.backoff_initial,
            backoff_max=settings.backoff_max,
            attempts=settings.rate_limit_attempts,
        )
        self.system = system_prompt(settings.level)
        self.guard_config = GuardrailConfig(settings.max_length_ratio, settings.min_length_slack)
        self.llm_calls = 0

    def _ask(self, user: str) -> str:
        self.llm_calls += 1
        return self.limiter.call(lambda: self.client.complete(self.system, user))

    def _get_raw(self, sentence: str) -> tuple[RawResult | None, str]:
        """Return a parsed reply, or (None, reason) after retries are exhausted."""
        key = cache_key(self.client.model_id, f"v{PROMPT_VERSION}\n{self.system}", sentence)
        if self.cache is not None and (cached := self.cache.get(key)) is not None:
            try:
                return parse_response(cached), ""
            except ParseError:
                self.cache.delete(key)  # stale or corrupt entry; ask again

        prompt = user_prompt(sentence)
        last_error = ""
        for attempt in range(1 + self.settings.max_retries):
            reply = self._ask(prompt)
            try:
                raw = parse_response(reply)
            except ParseError as exc:
                last_error = str(exc)
                log.warning("Malformed reply (attempt %d): %s", attempt + 1, last_error)
                prompt = _retry_prompt(sentence, last_error)
                continue
            if self.cache is not None:
                self.cache.put(key, self.client.model_id, reply)
            return raw, ""
        tries = 1 + self.settings.max_retries
        return None, f"the model returned malformed JSON {tries} times (last error: {last_error})"

    def check_sentence(self, sentence: Sentence) -> SentenceResult:
        """Check one sentence. Never raises except for fatal provider errors."""

        def flagged(reason: str) -> SentenceResult:
            return SentenceResult(sentence, Status.NEEDS_REVIEW, sentence.text, [], [reason])

        try:
            raw, error = self._get_raw(sentence.text)
        except RateLimitError as exc:
            return flagged(
                f"the provider was rate-limited, overloaded or timed out after retries ({exc}); "
                "run check again later (cached sentences are free)"
            )
        except LLMError as exc:
            if exc.fatal:
                raise
            return flagged(f"the provider returned an error: {exc}")
        if raw is None:
            return flagged(error)

        outcome = run_guardrails(sentence.text, sentence.index, raw, self.guard_config)
        if not outcome.passed:
            return SentenceResult(
                sentence, Status.NEEDS_REVIEW, raw.corrected, outcome.changes, outcome.reasons
            )
        status = Status.CHANGES_PROPOSED if outcome.changes else Status.NO_CHANGES
        return SentenceResult(sentence, status, raw.corrected, outcome.changes)

    def check_text(self, text: str, progress: ProgressFn | None = None) -> list[SentenceResult]:
        sentences = split_sentences(text)
        results: list[SentenceResult] = []
        for sentence in sentences:
            result = self.check_sentence(sentence)
            results.append(result)
            if progress is not None:
                progress(result, len(sentences))
        return results
