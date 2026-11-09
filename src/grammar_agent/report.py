"""Render ``report.md``, the document a human reads before approving changes."""

from __future__ import annotations

import re

from grammar_agent.models import Change, SentenceResult, Status
from grammar_agent.run import Run


def code(text: str) -> str:
    """Inline Markdown code that survives backticks and shows empty strings."""
    if text == "":
        return "*(nothing)*"
    longest = max((len(m) for m in re.findall(r"`+", text)), default=0)
    fence = "`" * (longest + 1)
    pad = " " if text.startswith("`") or text.endswith("`") else ""
    return f"{fence}{pad}{text}{pad}{fence}"


def quote(text: str) -> str:
    """A Markdown blockquote line; escape characters that would start Markdown syntax."""
    escaped = re.sub(r"([\\*_\[\]<>#|])", r"\\\1", text)
    return "> " + escaped.replace("\n", "\n> ")


def inline_diff(sentence: str, changes: list[Change]) -> str:
    """The sentence with each change shown as ~~old~~ **new**."""
    out: list[str] = []
    pos = 0
    for c in sorted(changes, key=lambda c: c.offset):
        out.append(sentence[pos : c.offset])
        old = f"~~{c.original_span}~~" if c.original_span else ""
        new = f"**{c.replacement}**" if c.replacement else ""
        out.append(f"{old}{new}<sup>[{c.id}]</sup>")
        pos = c.offset + len(c.original_span)
    out.append(sentence[pos:])
    return "".join(out)


def _sentence_section(r: SentenceResult) -> list[str]:
    s = r.sentence
    if r.status is Status.NO_CHANGES:
        return [f"### Sentence {s.index}: no changes", "", quote(s.text), ""]

    if r.status is Status.NEEDS_REVIEW:
        lines = [
            f"### Sentence {s.index}: needs manual review",
            "",
            "**Original (kept unchanged):**",
            "",
            quote(s.text),
            "",
        ]
        if r.corrected != s.text:
            lines += ["**Model suggestion (rejected, not offered for approval):**", ""]
            lines += [quote(r.corrected), ""]
        lines += ["**Why it was flagged:**", ""]
        lines += [f"- {reason}" for reason in r.review_reasons] + [""]
        return lines

    n = len(r.changes)
    lines = [
        f"### Sentence {s.index}: {n} change{'s' if n != 1 else ''}",
        "",
        "**Original:**",
        "",
        quote(s.text),
        "",
        "**Corrected:**",
        "",
        quote(r.corrected),
        "",
        f"**Changes:** {inline_diff(s.text, r.changes)}",
        "",
    ]
    for c in r.changes:
        # Name the category only when it adds something beyond the type.
        kind = (
            c.type
            if c.category in (c.type, "other")
            else f"{c.type}, {c.category.replace('_', ' ')}"
        )
        lines.append(
            f"- **[{c.id}]** *{kind}*: {code(c.original_span)} → {code(c.replacement)}. "
            f"{c.explanation}"
        )
    lines.append("")
    return lines


def render_report(run: Run, run_dir_hint: str = "<run-dir>") -> str:
    flagged = run.flagged
    with_changes = sum(1 for r in run.results if r.status is Status.CHANGES_PROPOSED)
    lines = [
        "# Grammar review report",
        "",
        f"- **Source:** {code(run.source_name)}",
        f"- **Model:** {code(run.model_id)}, explanation level: {run.level}",
        f"- **Generated:** {run.created_at}",
        "",
        "## Summary",
        "",
        "| | |",
        "|---|---|",
        f"| Sentences checked | {run.sentences_checked} |",
        f"| Changes proposed | {run.changes_proposed} (in {with_changes} sentences) |",
        f"| Sentences flagged for manual review | {len(flagged)} |",
        "",
    ]
    if flagged:
        ids = ", ".join(str(r.sentence.index) for r in flagged)
        lines += [
            f"Flagged sentences ({ids}) are left exactly as written. Check them yourself.",
            "",
        ]
    lines += [
        "Nothing has been changed yet. To accept or reject each numbered change, run:",
        "",
        "```bash",
        f"grammar-agent apply {run_dir_hint}",
        "```",
        "",
        "## Sentences",
        "",
    ]
    for r in run.results:
        lines += _sentence_section(r)
    return "\n".join(lines).rstrip() + "\n"
