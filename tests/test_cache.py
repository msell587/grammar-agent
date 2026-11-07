from pathlib import Path

from grammar_agent.cache import ResponseCache, cache_key


def test_key_depends_on_every_part() -> None:
    base = cache_key("m", "p", "s")
    assert base == cache_key("m", "p", "s")
    assert (
        len({base, cache_key("m2", "p", "s"), cache_key("m", "p2", "s"), cache_key("m", "p", "s2")})
        == 4
    )


def test_put_get_and_persist(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "cache.sqlite"
    with ResponseCache(path) as cache:
        assert cache.get("k") is None
        cache.put("k", "m", '{"a": 1}')
        assert cache.get("k") == '{"a": 1}'
        assert (cache.hits, cache.misses) == (1, 1)
    with ResponseCache(path) as reopened:
        assert reopened.get("k") == '{"a": 1}'
        assert len(reopened) == 1
        reopened.delete("k")
        assert len(reopened) == 0
