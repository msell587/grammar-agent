"""The approval step: a person decides on every change (or opts into --auto-approve)."""

from __future__ import annotations

from collections.abc import Callable

from grammar_agent.apply import reviewable_changes
from grammar_agent.models import Change, Decision, SentenceResult, Status
from grammar_agent.run import Run

InputFn = Callable[[str], str]
OutputFn = Callable[[str], None]

HELP = "  y = accept   n = reject   a = accept this and the rest of this sentence   q = quit"


class ReviewAborted(Exception):
    """The reviewer quit before deciding on every change. Nothing is written."""


def auto_approve(run: Run) -> list[Decision]:
    """Accept every change that passed the guardrails, marked as decided by 'auto'."""
    return [Decision(c.id, True, "auto") for c in reviewable_changes(run)]


def _marked(sentence: str, change: Change) -> str:
    end = change.offset + len(change.original_span)
    return (
        f"{sentence[: change.offset]}[{change.original_span} -> {change.replacement}]"
        f"{sentence[end:]}"
    )


def _review_sentence(
    r: SentenceResult, position: str, ask: InputFn, say: OutputFn
) -> list[Decision]:
    n = len(r.changes)
    say("")
    say(f"Sentence {r.sentence.index} ({position}, {n} change{'s' if n != 1 else ''})")
    say(f"  Original : {r.sentence.text}")
    say(f"  Corrected: {r.corrected}")
    decisions: list[Decision] = []
    accept_rest = False
    for c in r.changes:
        say("")
        say(f"  [{c.id}] {c.type}: {c.original_span!r} -> {c.replacement!r}")
        say(f"        {c.explanation}")
        say(f"        {_marked(r.sentence.text, c)}")
        if accept_rest:
            say("        accepted (accept all in sentence)")
            decisions.append(Decision(c.id, True, "human"))
            continue
        while True:
            answer = ask(f"  Accept [{c.id}]? [y/n/a/q/?] ").strip().lower()
            if answer in ("y", "yes"):
                decisions.append(Decision(c.id, True, "human"))
                break
            if answer in ("n", "no"):
                decisions.append(Decision(c.id, False, "human"))
                break
            if answer == "a":
                accept_rest = True
                decisions.append(Decision(c.id, True, "human"))
                break
            if answer in ("q", "quit"):
                raise ReviewAborted
            say(HELP)
    return decisions


def interactive_review(run: Run, ask: InputFn = input, say: OutputFn = print) -> list[Decision]:
    """Ask about every reviewable change. Raises ReviewAborted on quit, Ctrl-C or Ctrl-D."""
    to_review = [r for r in run.results if r.status is Status.CHANGES_PROPOSED]
    total = sum(len(r.changes) for r in to_review)
    say(f"{total} change(s) to review in {len(to_review)} sentence(s).")
    say(HELP)
    for r in run.flagged:
        say(f"Note: sentence {r.sentence.index} needs manual review and will be left unchanged.")

    decisions: list[Decision] = []
    try:
        for i, r in enumerate(to_review, start=1):
            decisions += _review_sentence(r, f"{i} of {len(to_review)}", ask, say)
    except (EOFError, KeyboardInterrupt) as exc:
        raise ReviewAborted from exc
    return decisions
