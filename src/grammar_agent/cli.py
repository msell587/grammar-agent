"""``grammar-agent check`` and ``grammar-agent apply``."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from grammar_agent import __version__
from grammar_agent.apply import DecisionError, write_outputs
from grammar_agent.cache import ResponseCache
from grammar_agent.checker import Checker
from grammar_agent.config import LEVELS, PROVIDERS, ConfigError, load_settings
from grammar_agent.llm import LLMClient, LLMError, make_client
from grammar_agent.models import SentenceResult, Status
from grammar_agent.report import render_report
from grammar_agent.review import ReviewAborted, auto_approve, interactive_review
from grammar_agent.run import (
    APPROVED_FILE,
    DECISIONS_FILE,
    REPORT_FILE,
    RESULTS_FILE,
    Run,
    load_run,
    save_run,
)


def _err(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="grammar-agent",
        description="Check spelling and grammar with an LLM; approve every change yourself.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="show debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="check a text file and write a review report")
    check.add_argument("input", nargs="?", default="-", help="a .txt file, or - for stdin")
    check.add_argument("--out", required=True, type=Path, help="run directory to write")
    check.add_argument("--provider", choices=PROVIDERS, help="override GRAMMAR_AGENT_PROVIDER")
    check.add_argument("--model", help="override the provider's model name")
    check.add_argument("--level", choices=LEVELS, help="explanation level (default intermediate)")
    check.add_argument("--delay", type=float, help="seconds between uncached requests")
    check.add_argument(
        "--max-length-ratio", type=float, help="reject corrections whose length changes more"
    )
    check.add_argument("--cache", type=Path, help="SQLite cache file")
    check.add_argument(
        "--mock-script", type=Path, help="JSON of scripted replies for --provider mock (demo)"
    )
    check.add_argument("--no-cache", action="store_true", help="always call the model")
    check.add_argument("--force", action="store_true", help="overwrite an existing run")

    apply = sub.add_parser("apply", help="review the changes and write approved.txt")
    apply.add_argument("run_dir", type=Path, help="directory written by `check`")
    apply.add_argument(
        "--auto-approve",
        action="store_true",
        help="accept every change that passed the guardrails (recorded as 'auto')",
    )
    apply.add_argument("--force", action="store_true", help="overwrite existing decisions")
    return parser


def _read_input(source: str) -> tuple[str, str]:
    if source == "-":
        if sys.stdin.isatty():
            raise ConfigError("no input file given and nothing piped on stdin")
        return "<stdin>", sys.stdin.read()
    path = Path(source)
    if not path.is_file():
        raise ConfigError(f"input file {path} does not exist")
    return path.name, path.read_text(encoding="utf-8")


def _progress(result: SentenceResult, total: int) -> None:
    label = {
        Status.NO_CHANGES: "no changes",
        Status.CHANGES_PROPOSED: f"{len(result.changes)} change(s) proposed",
        Status.NEEDS_REVIEW: "NEEDS MANUAL REVIEW",
    }[result.status]
    print(f"[{result.sentence.index}/{total}] {label}", file=sys.stderr)


def cmd_check(args: argparse.Namespace, client: LLMClient | None = None) -> int:
    settings = load_settings().with_overrides(
        provider=args.provider,
        model=args.model,
        level=args.level,
        request_delay=args.delay,
        max_length_ratio=args.max_length_ratio,
        cache_path=args.cache,
        mock_script=args.mock_script,
    )
    out: Path = args.out
    if (out / RESULTS_FILE).exists() and not args.force:
        raise ConfigError(f"{out} already contains a run; use --force or another --out")
    source_name, text = _read_input(args.input)
    client = client or make_client(settings)
    print(f"Checking {source_name} with {client.model_id} ...", file=sys.stderr)

    cache = None if args.no_cache else ResponseCache(settings.cache_path)
    try:
        checker = Checker(client, settings, cache)
        results = checker.check_text(text, _progress)
    finally:
        if cache is not None:
            cache.close()

    run = Run(source_name, text, client.model_id, settings.level, results)
    save_run(run, out)
    (out / REPORT_FILE).write_text(render_report(run, str(out)), encoding="utf-8")
    for stale in (DECISIONS_FILE, APPROVED_FILE):
        (out / stale).unlink(missing_ok=True)  # they belonged to the previous run

    hits = cache.hits if cache is not None else 0
    print(
        f"\nChecked {run.sentences_checked} sentences: {run.changes_proposed} change(s) "
        f"proposed, {len(run.flagged)} flagged for manual review.\n"
        f"Model calls: {checker.llm_calls}, cache hits: {hits}.\n"
        f"Report: {out / REPORT_FILE}\n"
        f"Next:   grammar-agent apply {out}",
        file=sys.stderr,
    )
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    run_dir: Path = args.run_dir
    run = load_run(run_dir)
    if (run_dir / DECISIONS_FILE).exists() and not args.force:
        raise ConfigError(f"{run_dir / DECISIONS_FILE} already exists; use --force to redo")
    if args.auto_approve:
        decisions, mode = auto_approve(run), "auto-approve"
    else:
        if not sys.stdin.isatty():
            raise ConfigError("interactive review needs a terminal; use --auto-approve")
        try:
            decisions, mode = interactive_review(run), "interactive"
        except ReviewAborted:
            print("\nReview stopped. Nothing was written.", file=sys.stderr)
            return 1
    write_outputs(run, decisions, run_dir, mode)
    accepted = sum(d.accepted for d in decisions)
    print(
        f"\n{accepted} of {len(decisions)} change(s) accepted "
        f"({len(run.flagged)} flagged sentence(s) left unchanged).\n"
        f"Wrote {run_dir / APPROVED_FILE} and {run_dir / DECISIONS_FILE}",
        file=sys.stderr,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    try:
        if args.command == "check":
            return cmd_check(args)
        return cmd_apply(args)
    except (ConfigError, LLMError, DecisionError, FileNotFoundError, ValueError) as exc:
        _err(str(exc))
        return 1
