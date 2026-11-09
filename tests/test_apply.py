import pytest

from grammar_agent.apply import DecisionError, build_approved_text, reviewable_changes
from grammar_agent.models import Change, Decision, Sentence, SentenceResult, Status
from grammar_agent.review import ReviewAborted, auto_approve, interactive_review
from grammar_agent.run import Run

SOURCE = "Teh cat sit on teh mat.\n\nShe dont care.  It is fine."


def _change(sid: int, n: int, span: str, repl: str, offset: int) -> Change:
    return Change(f"{sid}.{n}", span, repl, "spelling", "Because.", offset)


def make_run() -> Run:
    s1 = Sentence(1, "Teh cat sit on teh mat.", 0, 23)
    s2 = Sentence(2, "She dont care.", 25, 39)
    s3 = Sentence(3, "It is fine.", 41, 52)
    return Run(
        "sample.txt",
        SOURCE,
        "mock:mock",
        "intermediate",
        [
            SentenceResult(
                s1,
                Status.CHANGES_PROPOSED,
                "The cat sits on the mat.",
                [
                    _change(1, 1, "Teh", "The", 0),
                    _change(1, 2, "sit", "sits", 8),
                    _change(1, 3, "teh", "the", 15),
                ],
            ),
            SentenceResult(
                s2, Status.NEEDS_REVIEW, "She doesn't care at all.", [], ["meaning changed"]
            ),
            SentenceResult(s3, Status.NO_CHANGES, "It is fine."),
        ],
    )


def test_only_accepted_changes_are_applied() -> None:
    run = make_run()
    decisions = [
        Decision("1.1", True, "human"),
        Decision("1.2", False, "human"),
        Decision("1.3", True, "human"),
    ]
    assert build_approved_text(run, decisions) == (
        "The cat sit on the mat.\n\nShe dont care.  It is fine."
    )


def test_reject_all_returns_source_unchanged() -> None:
    run = make_run()
    decisions = [Decision(c.id, False, "human") for c in reviewable_changes(run)]
    assert build_approved_text(run, decisions) == SOURCE


def test_auto_approve_never_touches_flagged_sentences() -> None:
    run = make_run()
    decisions = auto_approve(run)
    assert {d.decided_by for d in decisions} == {"auto"}
    approved = build_approved_text(run, decisions)
    assert approved == "The cat sits on the mat.\n\nShe dont care.  It is fine."


def test_missing_decision_is_an_error() -> None:
    with pytest.raises(DecisionError, match="no decision"):
        build_approved_text(make_run(), [Decision("1.1", True, "human")])


def test_unknown_or_duplicate_decision_is_an_error() -> None:
    run = make_run()
    base = [Decision(c.id, True, "human") for c in reviewable_changes(run)]
    with pytest.raises(DecisionError, match="unknown"):
        build_approved_text(run, [*base, Decision("2.1", True, "human")])
    with pytest.raises(DecisionError, match="more than one"):
        build_approved_text(run, [*base, base[0]])


def test_tampered_source_is_detected() -> None:
    run = make_run()
    run.source_text = "X" + run.source_text
    with pytest.raises(DecisionError, match="no longer matches"):
        build_approved_text(run, auto_approve(run))


def scripted(answers: list[str]) -> tuple[list[str], object]:
    out: list[str] = []
    queue = list(answers)

    def ask(prompt: str) -> str:
        out.append(prompt)
        if not queue:
            raise EOFError
        return queue.pop(0)

    return out, ask


def test_interactive_accept_reject_and_help() -> None:
    out, ask = scripted(["?", "y", "n", "y"])
    decisions = interactive_review(make_run(), ask, out.append)  # type: ignore[arg-type]
    assert [(d.change_id, d.accepted, d.decided_by) for d in decisions] == [
        ("1.1", True, "human"),
        ("1.2", False, "human"),
        ("1.3", True, "human"),
    ]
    assert any("accept this and the rest" in line for line in out)
    assert any("sentence 2 needs manual review" in line for line in out)


def test_interactive_accept_rest_of_sentence() -> None:
    _, ask = scripted(["n", "a"])
    decisions = interactive_review(make_run(), ask, lambda _: None)  # type: ignore[arg-type]
    assert [d.accepted for d in decisions] == [False, True, True]


@pytest.mark.parametrize("answers", [["y", "q"], ["y"]])  # explicit quit, or Ctrl-D (EOF)
def test_interactive_quit_aborts(answers: list[str]) -> None:
    _, ask = scripted(answers)
    with pytest.raises(ReviewAborted):
        interactive_review(make_run(), ask, lambda _: None)  # type: ignore[arg-type]


def ids(decisions: list[Decision]) -> list[tuple[str, bool]]:
    return [(d.change_id, d.accepted) for d in decisions]


def test_explicit_accept_all_except() -> None:
    from grammar_agent.apply import decisions_from_lists

    decisions = decisions_from_lists(make_run(), "all", "[1.2]")
    assert ids(decisions) == [("1.1", True), ("1.2", False), ("1.3", True)]
    assert {d.decided_by for d in decisions} == {"human"}


def test_explicit_reject_all_except() -> None:
    from grammar_agent.apply import decisions_from_lists

    assert ids(decisions_from_lists(make_run(), "1.3", "all")) == [
        ("1.1", False),
        ("1.2", False),
        ("1.3", True),
    ]


def test_explicit_lists_must_cover_everything() -> None:
    from grammar_agent.apply import decisions_from_lists

    assert ids(decisions_from_lists(make_run(), "1.1, 1.3", "1.2"))[1] == ("1.2", False)
    with pytest.raises(DecisionError, match=r"not decided: 1\.3"):
        decisions_from_lists(make_run(), "1.1", "1.2")


@pytest.mark.parametrize(
    ("accept", "reject", "message"),
    [
        (None, None, "give --accept"),
        ("all", "all", "cannot both"),
        ("all", "9.9", "unknown"),
        ("2.1", "all", "unknown"),  # sentence 2 is flagged: not reviewable
        ("1.1,1.2,1.3", "1.1", "at once"),
    ],
)
def test_explicit_lists_errors(accept: str | None, reject: str | None, message: str) -> None:
    from grammar_agent.apply import decisions_from_lists

    with pytest.raises(DecisionError, match=message):
        decisions_from_lists(make_run(), accept, reject)


def test_change_from_dict_without_category_defaults_to_other() -> None:
    data = _change(1, 1, "teh", "the", 0).to_dict()
    del data["category"]
    assert Change.from_dict(data).category == "other"
