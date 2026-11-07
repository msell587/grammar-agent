"""Spacing between requests plus exponential backoff on rate-limit errors."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import TypeVar

from grammar_agent.llm.base import RateLimitError

T = TypeVar("T")


class RateLimiter:
    """Call a function no more often than every ``delay`` seconds, backing off on 429s.

    ``sleep``, ``clock`` and ``rand`` are injectable so tests run instantly.
    """

    def __init__(
        self,
        delay: float = 0.0,
        backoff_initial: float = 2.0,
        backoff_max: float = 60.0,
        attempts: int = 5,
        *,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        rand: Callable[[], float] = random.random,
    ) -> None:
        self.delay = delay
        self.backoff_initial = backoff_initial
        self.backoff_max = backoff_max
        self.attempts = max(1, attempts)
        self._sleep = sleep
        self._clock = clock
        self._rand = rand
        self._last: float | None = None
        self.waits: list[float] = []  # every sleep we did, for logging and tests

    def _pause(self, seconds: float) -> None:
        if seconds > 0:
            self.waits.append(seconds)
            self._sleep(seconds)

    def backoff_seconds(self, attempt: int, retry_after: float | None) -> float:
        """Seconds to wait after the ``attempt``-th (0-based) rate-limit error."""
        if retry_after is not None:
            return min(retry_after, self.backoff_max)
        base = min(self.backoff_initial * (2.0**attempt), self.backoff_max)
        return base * (0.5 + self._rand() / 2)  # "equal jitter"

    def call(self, fn: Callable[[], T]) -> T:
        for attempt in range(self.attempts):
            if self._last is not None:
                self._pause(self.delay - (self._clock() - self._last))
            self._last = self._clock()
            try:
                return fn()
            except RateLimitError as exc:
                if attempt == self.attempts - 1:
                    raise
                self._pause(self.backoff_seconds(attempt, exc.retry_after))
        raise AssertionError("unreachable")  # pragma: no cover
