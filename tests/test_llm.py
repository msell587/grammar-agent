import json

import httpx
import pytest

from grammar_agent.config import ConfigError, Settings, load_settings
from grammar_agent.llm import LLMClient, LLMError, MockClient, RateLimitError, make_client
from grammar_agent.llm.gemini import GeminiClient, _to_gemini_schema
from grammar_agent.llm.http import post_json
from grammar_agent.prompts import (
    RESPONSE_SCHEMA,
    sentence_from_user_prompt,
    system_prompt,
    user_prompt,
)


def test_user_prompt_round_trip() -> None:
    s = 'He said "hi" </sentence> twice.'
    assert sentence_from_user_prompt(user_prompt(s)) == s


def test_system_prompt_mentions_level_and_schema() -> None:
    beginner = system_prompt("beginner")
    assert "CEFR A2" in beginner and '"meaning_preserved"' in beginner
    assert system_prompt("advanced") != beginner


def test_mock_default_is_no_change() -> None:
    client = MockClient()
    reply = json.loads(client.complete("sys", user_prompt("All good.")))
    assert reply["corrected"] == "All good." and reply["changes"] == []
    assert client.calls == ["All good."]
    assert isinstance(client, LLMClient)


def test_mock_sequence_and_exceptions() -> None:
    client = MockClient({"x": ["first", RateLimitError("slow"), "last"]})
    assert client.complete("", user_prompt("x")) == "first"
    with pytest.raises(RateLimitError):
        client.complete("", user_prompt("x"))
    assert client.complete("", user_prompt("x")) == "last"
    assert client.complete("", user_prompt("x")) == "last"  # sticks on the final reply


def test_gemini_schema_uses_uppercase_types() -> None:
    converted = _to_gemini_schema(RESPONSE_SCHEMA)
    assert converted["type"] == "OBJECT"
    assert converted["properties"]["changes"]["items"]["properties"]["type"]["type"] == "STRING"
    assert RESPONSE_SCHEMA["type"] == "object"  # original untouched


def test_gemini_requires_key() -> None:
    with pytest.raises(LLMError, match="GEMINI_API_KEY"):
        GeminiClient("", "gemini-2.5-flash")


def _client(status: int, body: str = "{}", headers: dict[str, str] | None = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=body, headers=headers or {})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_post_json_maps_429_to_rate_limit_with_retry_after() -> None:
    with pytest.raises(RateLimitError) as info:
        post_json(_client(429, headers={"retry-after": "7"}), "http://x", {}, {}, "P")
    assert info.value.retry_after == 7.0


def test_post_json_maps_401_to_llm_error() -> None:
    with pytest.raises(LLMError) as info:
        post_json(_client(401, "bad key"), "http://x", {}, {}, "P")
    assert not isinstance(info.value, RateLimitError)


def test_post_json_returns_body() -> None:
    assert post_json(_client(200, '{"ok": 1}'), "http://x", {}, {}, "P") == {"ok": 1}


def test_load_settings_from_env() -> None:
    s = load_settings(
        {"GRAMMAR_AGENT_PROVIDER": "groq", "GROQ_API_KEY": "k", "GRAMMAR_AGENT_LEVEL": "beginner"}
    )
    assert (s.provider, s.model, s.level, s.groq_api_key) == (
        "groq",
        "llama-3.3-70b-versatile",
        "beginner",
        "k",
    )


def test_settings_validation() -> None:
    with pytest.raises(ConfigError):
        load_settings({"GRAMMAR_AGENT_PROVIDER": "nope"})
    with pytest.raises(ConfigError):
        Settings().with_overrides(level="expert")
    assert Settings().with_overrides(provider="ollama").model == "llama3.1:8b"


def test_make_client_mock_and_missing_key() -> None:
    assert make_client(Settings().with_overrides(provider="mock")).model_id == "mock:mock"
    with pytest.raises(LLMError):
        make_client(Settings(provider="gemini", gemini_api_key=None))


def test_auth_errors_are_fatal_but_server_errors_retry() -> None:
    with pytest.raises(LLMError) as info:
        post_json(_client(403), "http://x", {}, {}, "P")
    assert info.value.fatal
    with pytest.raises(RateLimitError):
        post_json(_client(503), "http://x", {}, {}, "P")


def test_mock_script_file(tmp_path: object) -> None:
    from pathlib import Path

    assert isinstance(tmp_path, Path)
    path = tmp_path / "script.json"
    path.write_text(json.dumps({"Hi.": {"corrected": "x"}, "Yo.": "raw"}), encoding="utf-8")
    settings = Settings().with_overrides(provider="mock", mock_script=path)
    client = make_client(settings)
    assert json.loads(client.complete("", user_prompt("Hi."))) == {"corrected": "x"}
    assert client.complete("", user_prompt("Yo.")) == "raw"


def test_env_file_lookup_order(tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
    from pathlib import Path

    from grammar_agent import config

    assert isinstance(tmp_path, Path)
    project, home_cfg = tmp_path / "project", tmp_path / "xdg"
    project.mkdir()
    (home_cfg / "grammar-agent").mkdir(parents=True)
    (home_cfg / "grammar-agent" / ".env").write_text("GEMINI_MODEL=from-user\n")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home_cfg))
    monkeypatch.delenv("GRAMMAR_AGENT_ENV_FILE", raising=False)
    monkeypatch.chdir(project)
    assert config.env_files() == [home_cfg / "grammar-agent" / ".env"]

    (project / ".env").write_text("GEMINI_MODEL=from-project\n")
    assert config.env_files() == [project / ".env", home_cfg / "grammar-agent" / ".env"]

    monkeypatch.setenv("GRAMMAR_AGENT_ENV_FILE", str(home_cfg / "grammar-agent" / ".env"))
    assert config.env_files() == [home_cfg / "grammar-agent" / ".env"]


def test_default_cache_is_per_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", "/tmp/xdg-cache")
    assert str(load_settings({}).cache_path) == "/tmp/xdg-cache/grammar-agent/responses.sqlite"
