"""Turn decisions into ``approved.txt`` and an auditable ``decisions.json``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from grammar_agent.models import Change, Decision, Status
from grammar_agent.run import APPROVED_FILE, DECISIONS_FILE, Run, now_iso


class DecisionError(ValueError):
    """Decisions are missing, duplicated, or refer to changes that do not exist."""


def reviewable_changes(run: Run) -> list[Change]:
    """Changes that may be approved: only those in sentences that passed every guardrail."""
    return [c for r in run.results if r.status is Status.CHANGES_PROPOSED for c in r.changes]


def validate_decisions(run: Run, decisions: list[Decision]) -> None:
    """Every reviewable change must have exactly one decision, and nothing else may."""
    expected = {c.id for c in reviewable_changes(run)}
    seen: set[str] = set()
    for d in decisions:
        if d.change_id not in expected:
            raise DecisionError(f"decision for unknown or non-reviewable change {d.change_id}")
        if d.change_id in seen:
            raise DecisionError(f"more than one decision for change {d.change_id}")
        seen.add(d.change_id)
    missing = expected - seen
    if missing:
        raise DecisionError(f"no decision for changes: {', '.join(sorted(missing))}")


def build_approved_text(run: Run, decisions: list[Decision]) -> str:
    """Apply only explicitly accepted changes to the original text, in place."""
    validate_decisions(run, decisions)
    accepted = {d.change_id for d in decisions if d.accepted}
    edits: list[tuple[int, Change]] = []
    for r in run.results:
        if r.status is not Status.CHANGES_PROPOSED:
            continue  # flagged sentences are never modified
        for c in r.changes:
            if c.id in accepted:
                edits.append((r.sentence.start + c.offset, c))

    text = run.source_text
    out: list[str] = []
    pos = 0
    for start, c in sorted(edits, key=lambda e: e[0]):
        end = start + len(c.original_span)
        if text[start:end] != c.original_span or start < pos:
            raise DecisionError(f"change {c.id} no longer matches the source text")
        replacement = c.replacement
        out.append(text[pos:start])
        out.append(replacement)
        pos = end
    out.append(text[pos:])
    return "".join(out)


def decisions_document(run: Run, decisions: list[Decision], mode: str) -> dict[str, Any]:
    by_id = {c.id: c for c in reviewable_changes(run)}
    return {
        "created_at": now_iso(),
        "mode": mode,
        "source_name": run.source_name,
        "model": run.model_id,
        "summary": {
            "accepted": sum(d.accepted for d in decisions),
            "rejected": sum(not d.accepted for d in decisions),
            "flagged_sentences_left_unchanged": [r.sentence.index for r in run.flagged],
        },
        "decisions": [
            {
                **d.to_dict(),
                "type": by_id[d.change_id].type,
                "original_span": by_id[d.change_id].original_span,
                "replacement": by_id[d.change_id].replacement,
            }
            for d in decisions
        ],
    }


def write_outputs(run: Run, decisions: list[Decision], run_dir: Path, mode: str) -> str:
    """Validate, then write ``approved.txt`` and ``decisions.json``. Returns the approved text."""
    approved = build_approved_text(run, decisions)
    doc = decisions_document(run, decisions, mode)
    (run_dir / DECISIONS_FILE).write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n", "utf-8"
    )
    (run_dir / APPROVED_FILE).write_text(approved, encoding="utf-8")
    return approved
