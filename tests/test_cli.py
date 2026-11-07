import json
import os
from pathlib import Path

import pytest

from grammar_agent import cli
from grammar_agent.config import Settings, load_settings


@pytest.fixture(autouse=True)
def mock_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for var in ("GEMINI_API_KEY", "GROQ_API_KEY", "GRAMMAR_AGENT_LEVEL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("GRAMMAR_AGENT_PROVIDER", "mock")
    monkeypatch.setenv("GRAMMAR_AGENT_REQUEST_DELAY", "0")
    monkeypatch.setenv("GRAMMAR_AGENT_CACHE", str(tmp_path / "cache.sqlite"))

    # Read only the patched environment: never a developer's real .env file.
    def env_only() -> Settings:
        return load_settings(dict(os.environ))

    monkeypatch.setattr(cli, "load_settings", env_only)


def test_check_then_apply_auto(tmp_path: Path) -> None:
    src = tmp_path / "in.txt"
    src.write_text("Hello there. All good.\n", encoding="utf-8")
    out = tmp_path / "run1"
    assert cli.main(["check", str(src), "--out", str(out)]) == 0
    assert (out / "report.md").exists() and (out / "results.json").exists()
    assert cli.main(["apply", str(out), "--auto-approve"]) == 0
    assert (out / "approved.txt").read_text(encoding="utf-8") == "Hello there. All good.\n"
    assert json.loads((out / "decisions.json").read_text())["mode"] == "auto-approve"
    # Decisions are not silently overwritten.
    assert cli.main(["apply", str(out), "--auto-approve"]) == 1


def test_check_refuses_to_overwrite(tmp_path: Path) -> None:
    src = tmp_path / "in.txt"
    src.write_text("Hi.", encoding="utf-8")
    out = tmp_path / "run"
    assert cli.main(["check", str(src), "--out", str(out)]) == 0
    assert cli.main(["check", str(src), "--out", str(out)]) == 1
    assert cli.main(["check", str(src), "--out", str(out), "--force"]) == 0


def test_missing_input_and_missing_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["check", str(tmp_path / "nope.txt"), "--out", str(tmp_path / "r")]) == 1
    assert cli.main(["apply", str(tmp_path / "empty")]) == 1
    assert "does not exist" in capsys.readouterr().err


def test_missing_api_key_is_a_clean_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    src = tmp_path / "in.txt"
    src.write_text("Hi.", encoding="utf-8")
    code = cli.main(["check", str(src), "--out", str(tmp_path / "r"), "--provider", "gemini"])
    assert code == 1
    assert "GEMINI_API_KEY" in capsys.readouterr().err


def test_apply_with_explicit_ids(tmp_path: Path) -> None:
    script = tmp_path / "script.json"
    script.write_text(
        json.dumps(
            {
                "Teh cat sat.": {
                    "original": "Teh cat sat.",
                    "corrected": "The cat sat.",
                    "meaning_preserved": True,
                    "changes": [
                        {
                            "original_span": "Teh",
                            "replacement": "The",
                            "type": "spelling",
                            "explanation": "Typo.",
                        }
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    src = tmp_path / "in.txt"
    src.write_text("Teh cat sat.", encoding="utf-8")
    out = tmp_path / "run"
    assert cli.main(["check", str(src), "--out", str(out), "--mock-script", str(script)]) == 0
    assert cli.main(["apply", str(out), "--accept", "all", "--auto-approve"]) == 1
    assert cli.main(["apply", str(out), "--reject", "all"]) == 0
    assert (out / "approved.txt").read_text(encoding="utf-8") == "Teh cat sat."
    assert cli.main(["apply", str(out), "--accept", "1.1", "--force"]) == 0
    assert (out / "approved.txt").read_text(encoding="utf-8") == "The cat sat."
    doc = json.loads((out / "decisions.json").read_text())
    assert doc["mode"] == "explicit-ids"
    assert doc["decisions"][0]["decided_by"] == "human"
