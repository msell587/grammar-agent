"""Checks that decide whether a model's correction can be offered for approval.

A correction that fails any check is not discarded silently: the sentence is
marked "needs manual review" with the reasons, and its text is left unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import pairwise

from grammar_agent.models import Change
from grammar_agent.parsing import RawResult


@dataclass(frozen=True)
class GuardrailConfig:
    max_length_ratio: float = 0.30
    min_length_slack: int = 12


@dataclass
class GuardrailOutcome:
    changes: list[Change] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.reasons


def _norm(text: str) -> str:
    return " ".join(text.split())


def apply_changes(text: str, changes: list[Change]) -> str:
    """Apply located changes (sorted, non-overlapping) to ``text``."""
    out: list[str] = []
    pos = 0
    for c in sorted(changes, key=lambda c: c.offset):
        out.append(text[pos : c.offset])
        out.append(c.replacement)
        pos = c.offset + len(c.original_span)
    out.append(text[pos:])
    return "".join(out)


def check_length_ratio(original: str, corrected: str, config: GuardrailConfig) -> str | None:
    diff = abs(len(corrected) - len(original))
    ratio = diff / max(len(original), 1)
    if diff > config.min_length_slack and ratio > config.max_length_ratio:
        return (
            f"corrected text length changed by {ratio:.0%} ({diff} characters), more than the "
            f"{config.max_length_ratio:.0%} limit; this looks like a rewrite"
        )
    return None


def locate_changes(sentence: str, sentence_index: int, raw: RawResult) -> GuardrailOutcome:
    """Find each ``original_span`` verbatim in the sentence and give it an id and offset."""
    outcome = GuardrailOutcome()
    cursor = 0
    located: list[Change] = []
    for raw_change in raw.changes:
        span = raw_change.original_span
        if span == raw_change.replacement:
            continue  # a no-op "change"; ignore it
        if not span:
            outcome.reasons.append(
                f"a change has an empty original_span (replacement {raw_change.replacement!r}), "
                "so it cannot be located"
            )
            continue
        offset = sentence.find(span, cursor)
        if offset == -1:
            offset = sentence.find(span)  # the model may list changes out of order
        if offset == -1:
            outcome.reasons.append(f"original_span {span!r} was not found verbatim in the sentence")
            continue
        cursor = offset + len(span)
        located.append(
            Change(
                id="",
                original_span=span,
                replacement=raw_change.replacement,
                type=raw_change.type,
                explanation=raw_change.explanation,
                offset=offset,
            )
        )

    located.sort(key=lambda c: c.offset)
    for prev, nxt in pairwise(located):
        if nxt.offset < prev.offset + len(prev.original_span):
            outcome.reasons.append(
                f"changes overlap ({prev.original_span!r} and {nxt.original_span!r})"
            )
    outcome.changes = [
        Change(
            id=f"{sentence_index}.{n}",
            original_span=c.original_span,
            replacement=c.replacement,
            type=c.type,
            explanation=c.explanation,
            offset=c.offset,
        )
        for n, c in enumerate(located, start=1)
    ]
    return outcome


def run_guardrails(
    sentence: str, sentence_index: int, raw: RawResult, config: GuardrailConfig
) -> GuardrailOutcome:
    """Run every check; the outcome lists all reasons, not just the first."""
    outcome = locate_changes(sentence, sentence_index, raw)
    reasons = outcome.reasons

    if not raw.meaning_preserved:
        reasons.insert(0, "the model reported that its correction may change the meaning")
    if _norm(raw.original) != _norm(sentence):
        reasons.append("the model's copy of the original sentence does not match the input")
    length_reason = check_length_ratio(sentence, raw.corrected, config)
    if length_reason:
        reasons.append(length_reason)
    if not reasons and apply_changes(sentence, outcome.changes) != raw.corrected:
        reasons.append(
            "the listed changes do not produce the model's corrected sentence "
            "(the model made edits it did not explain)"
        )
    for c in outcome.changes:
        if not c.explanation:
            reasons.append(f"change {c.id} has no explanation")
    return outcome
