import pytest

from grammar_agent.llm.base import RateLimitError
from grammar_agent.ratelimit import RateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def limiter(fake: FakeClock, **kw: float) -> RateLimiter:
    return RateLimiter(sleep=fake.sleep, clock=fake.clock, rand=lambda: 1.0, **kw)  # type: ignore[arg-type]


def test_delay_between_requests() -> None:
    fake = FakeClock()
    rl = limiter(fake, delay=5.0)
    rl.call(lambda: 1)
    fake.now += 2.0
    rl.call(lambda: 2)
    assert fake.slept == [3.0]


def test_exponential_backoff_then_success() -> None:
    fake = FakeClock()
    rl = limiter(fake, backoff_initial=1.0, backoff_max=60.0, attempts=4)
    outcomes: list[object] = [RateLimitError("a"), RateLimitError("b"), "ok"]

    def fn() -> str:
        item = outcomes.pop(0)
        if isinstance(item, Exception):
            raise item
        return str(item)

    assert rl.call(fn) == "ok"
    assert fake.slept == [1.0, 2.0]  # 1 * 2**0, 1 * 2**1 (jitter fixed at max)


def test_retry_after_header_wins_and_is_capped() -> None:
    fake = FakeClock()
    rl = limiter(fake, backoff_max=10.0, attempts=3)
    errors = [RateLimitError("x", retry_after=4.0), RateLimitError("y", retry_after=99.0)]

    def fn() -> str:
        if errors:
            raise errors.pop(0)
        return "ok"

    assert rl.call(fn) == "ok"
    assert fake.slept == [4.0, 10.0]


def test_gives_up_after_attempts() -> None:
    fake = FakeClock()
    rl = limiter(fake, attempts=3)

    def fn() -> str:
        raise RateLimitError("always")

    with pytest.raises(RateLimitError):
        rl.call(fn)
    assert len(fake.slept) == 2
