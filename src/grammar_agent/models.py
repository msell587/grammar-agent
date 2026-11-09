"""Plain data types shared across the pipeline.

Everything here is a dataclass with explicit ``to_dict``/``from_dict`` so that a
run directory (``results.json``, ``decisions.json``) can be written by ``check``
and read back by ``apply`` without pickling or any extra dependency.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

CHANGE_TYPES = ("spelling", "grammar", "punctuation", "other")

# Finer-grained mistake categories, so learners can see which kinds of mistakes they repeat.
MISTAKE_CATEGORIES = (
    "verb_tense",
    "subject_verb_agreement",
    "articles",
    "prepositions",
    "plurals",
    "word_order",
    "word_choice",
    "pronouns",
    "spelling",
    "punctuation",
    "capitalization",
    "other",
)


class Status(StrEnum):
    """Outcome of checking one sentence."""

    NO_CHANGES = "no_changes"
    CHANGES_PROPOSED = "changes_proposed"
    NEEDS_REVIEW = "needs_manual_review"


@dataclass(frozen=True)
class Sentence:
    """A sentence and its position in the source text.

    ``start``/``end`` are character offsets into the original text, so approved
    changes can be applied in place and all other whitespace is preserved.
    """

    index: int  # 1-based, used for change ids like [3.2]
    text: str
    start: int
    end: int


@dataclass(frozen=True)
class Change:
    """One proposed edit, located inside its sentence."""

    id: str  # "<sentence>.<n>", e.g. "3.2"
    original_span: str
    replacement: str
    type: str
    explanation: str
    offset: int  # where original_span starts inside the sentence text
    category: str = "other"  # one of MISTAKE_CATEGORIES

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Change:
        return cls(
            id=str(data["id"]),
            original_span=str(data["original_span"]),
            replacement=str(data["replacement"]),
            type=str(data["type"]),
            explanation=str(data["explanation"]),
            offset=int(data["offset"]),
            # Results written before categories existed have none.
            category=str(data.get("category", "other")),
        )


@dataclass
class SentenceResult:
    """The checked (and guarded) outcome for one sentence."""

    sentence: Sentence
    status: Status
    corrected: str
    changes: list[Change] = field(default_factory=list)
    review_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sentence": asdict(self.sentence),
            "status": self.status.value,
            "corrected": self.corrected,
            "changes": [c.to_dict() for c in self.changes],
            "review_reasons": list(self.review_reasons),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SentenceResult:
        s = data["sentence"]
        return cls(
            sentence=Sentence(
                index=int(s["index"]), text=str(s["text"]), start=int(s["start"]), end=int(s["end"])
            ),
            status=Status(data["status"]),
            corrected=str(data["corrected"]),
            changes=[Change.from_dict(c) for c in data["changes"]],
            review_reasons=[str(r) for r in data["review_reasons"]],
        )


@dataclass(frozen=True)
class Decision:
    """A human (or explicitly auto-approved) verdict on one change."""

    change_id: str
    accepted: bool
    decided_by: str  # "human" or "auto"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Decision:
        return cls(
            change_id=str(data["change_id"]),
            accepted=bool(data["accepted"]),
            decided_by=str(data["decided_by"]),
        )
