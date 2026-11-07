from grammar_agent.report import code, inline_diff, quote, render_report
from grammar_agent.run import Run, load_run, save_run
from tests.test_apply import make_run


def test_summary_counts() -> None:
    report = render_report(make_run(), "./run1")
    assert "| Sentences checked | 3 |" in report
    assert "| Changes proposed | 3 (in 1 sentences) |" in report
    assert "| Sentences flagged for manual review | 1 |" in report
    assert "grammar-agent apply ./run1" in report


def test_numbered_changes_and_flagged_section() -> None:
    report = render_report(make_run())
    assert "**[1.2]** *spelling*: `sit` → `sits`. Because." in report
    assert "### Sentence 2: needs manual review" in report
    assert "- meaning changed" in report
    assert "### Sentence 3: no changes" in report


def test_markdown_helpers() -> None:
    assert code("a`b") == "``a`b``"
    assert code("") == "*(nothing)*"
    assert quote("*not bold*") == r"> \*not bold\*"
    run = make_run()
    first = run.results[0]
    assert inline_diff(first.sentence.text, first.changes[:1]).startswith(
        "~~Teh~~**The**<sup>[1.1]</sup> cat"
    )


def test_run_round_trip(tmp_path: object) -> None:
    from pathlib import Path

    assert isinstance(tmp_path, Path)
    run = make_run()
    save_run(run, tmp_path)
    loaded: Run = load_run(tmp_path)
    assert loaded.to_dict() == run.to_dict()
