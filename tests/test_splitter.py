from grammar_agent.splitter import split_sentences


def texts(text: str) -> list[str]:
    return [s.text for s in split_sentences(text)]


def test_basic_split() -> None:
    assert texts("Hello there. How are you? I am fine!") == [
        "Hello there.",
        "How are you?",
        "I am fine!",
    ]


def test_offsets_point_back_into_source() -> None:
    text = "  First one.   Second one.\n\nThird."
    for s in split_sentences(text):
        assert text[s.start : s.end] == s.text
    assert [s.index for s in split_sentences(text)] == [1, 2, 3]


def test_last_sentence_without_punctuation() -> None:
    assert texts("One. Two without a dot") == ["One.", "Two without a dot"]


def test_abbreviations_and_initials_do_not_split() -> None:
    assert texts("Dr. Smith met J. R. Tolkien. They talked.") == [
        "Dr. Smith met J. R. Tolkien.",
        "They talked.",
    ]
    assert texts("Bring fruit, e.g. Apples. Then leave.") == [
        "Bring fruit, e.g. Apples.",
        "Then leave.",
    ]


def test_lowercase_continuation_does_not_split() -> None:
    assert texts('"Why?" she asked. Nobody knew.') == ['"Why?" she asked.', "Nobody knew."]


def test_closing_quote_stays_with_sentence() -> None:
    assert texts('He said "stop." Then he left.') == ['He said "stop."', "Then he left."]


def test_decimals_do_not_split() -> None:
    assert texts("Pi is 3.14 roughly. Yes.") == ["Pi is 3.14 roughly.", "Yes."]


def test_paragraph_break_ends_sentence() -> None:
    assert texts("A heading\n\nBody text here.") == ["A heading", "Body text here."]


def test_list_items_split() -> None:
    text = "Shopping list:\n- eggs\n- milk\n1. first\n2) second"
    assert texts(text) == ["Shopping list:", "- eggs", "- milk", "1. first", "2) second"]


def test_empty_and_whitespace() -> None:
    assert split_sentences("") == []
    assert split_sentences("   \n\n  ") == []


def test_known_weakness_unlisted_abbreviation() -> None:
    # Documented weakness: "Corp." is not in the list, so this splits too early.
    assert texts("Acme Corp. Makes things.") == ["Acme Corp.", "Makes things."]
