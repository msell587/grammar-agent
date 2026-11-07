"""Reading and writing a run directory.

A run directory holds everything needed to audit one check:

* ``results.json``: the source text plus every checked sentence (written by ``check``)
* ``report.md``: the human-readable review report (written by ``check``)
* ``decisions.json``: every accept/reject decision (written by ``apply``)
* ``approved.txt``: the source with only the approved changes applied (written by ``apply``)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from grammar_agent.models import SentenceResult, Status

RESULTS_FILE = "results.json"
REPORT_FILE = "report.md"
DECISIONS_FILE = "decisions.json"
APPROVED_FILE = "approved.txt"
FORMAT_VERSION = 1


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


@dataclass
class Run:
    source_name: str
    source_text: str
    model_id: str
    level: str
    results: list[SentenceResult]
    created_at: str = field(default_factory=now_iso)

    @property
    def sentences_checked(self) -> int:
        return len(self.results)

    @property
    def changes_proposed(self) -> int:
        return sum(len(r.changes) for r in self.results if r.status is Status.CHANGES_PROPOSED)

    @property
    def flagged(self) -> list[SentenceResult]:
        return [r for r in self.results if r.status is Status.NEEDS_REVIEW]

    def to_dict(self) -> dict[str, Any]:
        return {
            "format_version": FORMAT_VERSION,
            "created_at": self.created_at,
            "source_name": self.source_name,
            "model": self.model_id,
            "level": self.level,
            "source_text": self.source_text,
            "results": [r.to_dict() for r in self.results],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Run:
        if data.get("format_version") != FORMAT_VERSION:
            raise ValueError(f"unsupported results format {data.get('format_version')!r}")
        return cls(
            source_name=str(data["source_name"]),
            source_text=str(data["source_text"]),
            model_id=str(data["model"]),
            level=str(data["level"]),
            results=[SentenceResult.from_dict(r) for r in data["results"]],
            created_at=str(data["created_at"]),
        )


def save_run(run: Run, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / RESULTS_FILE
    path.write_text(json.dumps(run.to_dict(), indent=2, ensure_ascii=False) + "\n", "utf-8")
    return path


def load_run(run_dir: Path) -> Run:
    path = run_dir / RESULTS_FILE
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run `grammar-agent check` first.")
    data: dict[str, Any] = json.loads(path.read_text("utf-8"))
    return Run.from_dict(data)
