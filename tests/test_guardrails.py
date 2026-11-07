from grammar_agent.guardrails import GuardrailConfig, apply_changes, run_guardrails
from grammar_agent.parsing import RawChange, RawResult

CONFIG = GuardrailConfig(max_length_ratio=0.30, min_length_slack=12)


def raw(
    original: str,
    corrected: str,
    changes: list[tuple[str, str]],
    meaning_preserved: bool = True,
) -> RawResult:
    return RawResult(
        original=original,
        corrected=corrected,
        meaning_preserved=meaning_preserved,
        changes=[RawChange(a, b, "spelling", "Fix it.") for a, b in changes],
    )


def test_valid_correction_passes_with_ids_and_offsets() -> None:
    s = "Teh cat sat on teh mat."
    out = run_guardrails(
        s, 4, raw(s, "The cat sat on the mat.", [("Teh", "The"), ("teh", "the")]), CONFIG
    )
    assert out.passed
    assert [(c.id, c.offset) for c in out.changes] == [("4.1", 0), ("4.2", 15)]
    assert apply_changes(s, out.changes) == "The cat sat on the mat."


def test_no_changes_passes() -> None:
    s = "All is well."
    out = run_guardrails(s, 1, raw(s, s, []), CONFIG)
    assert out.passed and out.changes == []


def test_meaning_not_preserved_is_rejected() -> None:
    s = "I like cats."
    out = run_guardrails(s, 1, raw(s, "I like dogs.", [("cats", "dogs")], False), CONFIG)
    assert not out.passed
    assert "meaning" in out.reasons[0]


def test_span_not_found_is_rejected() -> None:
    s = "She go to school."
    out = run_guardrails(s, 1, raw(s, "She goes to school.", [("she go", "she goes")]), CONFIG)
    assert any("not found verbatim" in r for r in out.reasons)


def test_length_ratio_rejects_rewrites() -> None:
    s = "It is good."
    rewrite = "It is genuinely and remarkably excellent in every way."
    out = run_guardrails(s, 1, raw(s, rewrite, [("good", rewrite[6:-1])]), CONFIG)
    assert any("looks like a rewrite" in r for r in out.reasons)


def test_length_ratio_allows_small_fix_in_short_sentence() -> None:
    # 1 char on a 3-char sentence is 33%, but under the absolute slack of 12 chars.
    s = "Its"
    out = run_guardrails(s, 1, raw(s, "It's", [("Its", "It's")]), CONFIG)
    assert out.passed


def test_unexplained_edits_are_rejected() -> None:
    s = "Teh cat sat."
    out = run_guardrails(s, 1, raw(s, "The cat sits.", [("Teh", "The")]), CONFIG)
    assert any("did not explain" in r for r in out.reasons)


def test_corrected_differs_but_no_changes_is_rejected() -> None:
    s = "Teh cat."
    out = run_guardrails(s, 1, raw(s, "The cat.", []), CONFIG)
    assert not out.passed


def test_overlapping_changes_are_rejected() -> None:
    s = "abcdef"
    out = run_guardrails(s, 1, raw(s, "xyz", [("abcd", "x"), ("cdef", "y")]), CONFIG)
    assert any("overlap" in r for r in out.reasons)


def test_original_echo_mismatch_is_rejected() -> None:
    out = run_guardrails("Hello.", 1, raw("Goodbye.", "Goodbye.", []), CONFIG)
    assert any("does not match the input" in r for r in out.reasons)


def test_repeated_span_is_located_in_order() -> None:
    s = "its fine and its done."
    out = run_guardrails(
        s, 2, raw(s, "it's fine and it's done.", [("its", "it's"), ("its", "it's")]), CONFIG
    )
    assert out.passed
    assert [c.offset for c in out.changes] == [0, 13]


def test_empty_span_is_rejected() -> None:
    s = "Hello world"
    out = run_guardrails(s, 1, raw(s, "Hello world.", [("", ".")]), CONFIG)
    assert any("empty original_span" in r for r in out.reasons)


def test_noop_change_is_ignored() -> None:
    s = "Fine."
    out = run_guardrails(s, 1, raw(s, s, [("Fine", "Fine")]), CONFIG)
    assert out.passed and out.changes == []
