"""A scripted client for tests and offline demos. It never touches the network."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from grammar_agent.prompts import sentence_from_user_prompt

# A scripted reply is raw text, or an exception to raise (e.g. RateLimitError).
Reply = str | BaseException
Script = Reply | Sequence[Reply] | Callable[[str], Reply]


def load_script(path: Path) -> dict[str, Script]:
    """Load ``{sentence: reply}`` from JSON; a reply may be an object or raw text."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object mapping sentences to replies")
    return {
        str(sentence): reply if isinstance(reply, str) else json.dumps(reply)
        for sentence, reply in data.items()
    }


def no_change_reply(sentence: str) -> str:
    return json.dumps(
        {"original": sentence, "corrected": sentence, "meaning_preserved": True, "changes": []}
    )


class MockClient:
    """Return scripted replies keyed by sentence.

    * a ``str`` reply is returned every time that sentence is checked;
    * a sequence of replies is consumed one per call (handy for testing retries);
    * a callable receives the sentence and returns a reply;
    * any reply that is an exception is raised instead of returned.

    Sentences without a script get a valid "no errors" reply.
    """

    def __init__(self, script: Mapping[str, Script] | None = None, model: str = "mock") -> None:
        self._script: dict[str, Script] = dict(script or {})
        self._cursor: dict[str, int] = {}
        self._model = model
        self.calls: list[str] = []

    @property
    def model_id(self) -> str:
        return f"mock:{self._model}"

    def complete(self, system: str, user: str) -> str:
        sentence = sentence_from_user_prompt(user)
        self.calls.append(sentence)
        entry = self._script.get(sentence)
        reply: Reply
        if entry is None:
            reply = no_change_reply(sentence)
        elif isinstance(entry, str | BaseException):
            reply = entry
        elif callable(entry):
            reply = entry(sentence)
        else:
            i = self._cursor.get(sentence, 0)
            self._cursor[sentence] = i + 1
            reply = entry[min(i, len(entry) - 1)]
        if isinstance(reply, BaseException):
            raise reply
        return reply
