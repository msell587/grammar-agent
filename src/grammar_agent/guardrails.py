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


# Typographic quotes and their ASCII forms. Each maps one character to one character, so
# offsets found in folded text are valid in the original text too.
_QUOTE_FOLD = str.maketrans(
    {chr(0x2018): "'", chr(0x2019): "'", chr(0x201C): '"', chr(0x201D): '"'}
)
_CURLY = frozenset(chr(c) for c in (0x2018, 0x2019, 0x201C, 0x201D))


def fold_quotes(text: str) -> str:
    """Replace curly quotes with straight ones (same length)."""
    return text.translate(_QUOTE_FOLD)


def _norm(text: str) -> str:
    return " ".join(fold_quotes(text).split())


def _match_quote_style(replacement: str, sentence: str) -> str:
    """Use curly quotes in the replacement if the sentence is written with curly quotes only.

    Models often answer with straight quotes even when the source uses curly ones (as Mac and
    phone keyboards type by default); without this, an accepted fix would mix the two styles.
    """
    uses_curly = any(ch in _CURLY for ch in sentence)
    if not uses_curly or "'" in sentence or '"' in sentence:
        return replacement
    out: list[str] = []
    for i, ch in enumerate(replacement):
        if ch == "'":
            out.append(chr(0x2019))
        elif ch == '"':
            before = replacement[i - 1] if i else " "
            out.append(chr(0x201C) if before.isspace() or before in "([" else chr(0x201D))
        else:
            out.append(ch)
    return "".join(out)


def _find(sentence: str, span: str, cursor: int) -> int:
    """Find ``span`` at/after ``cursor``, then anywhere; then the same ignoring quote style."""
    for haystack, needle in ((sentence, span), (fold_quotes(sentence), fold_quotes(span))):
        offset = haystack.find(needle, cursor)
        if offset == -1:
            offset = haystack.find(needle)  # the model may list changes out of order
        if offset != -1:
            return offset
    return -1


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
        offset = _find(sentence, span, cursor)
        if offset == -1:
            outcome.reasons.append(f"original_span {span!r} was not found verbatim in the sentence")
            continue
        span = sentence[offset : offset + len(span)]  # the source's exact characters
        cursor = offset + len(span)
        located.append(
            Change(
                id="",
                original_span=span,
                replacement=_match_quote_style(raw_change.replacement, sentence),
                type=raw_change.type,
                explanation=raw_change.explanation,
                offset=offset,
                category=raw_change.category,
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
            category=c.category,
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
    applied = fold_quotes(apply_changes(sentence, outcome.changes))
    if not reasons and applied != fold_quotes(raw.corrected):
        reasons.append(
            "the listed changes do not produce the model's corrected sentence "
            "(the model made edits it did not explain)"
        )
    for c in outcome.changes:
        if not c.explanation:
            reasons.append(f"change {c.id} has no explanation")
    return outcome
