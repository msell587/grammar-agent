"""A small, dependency-free sentence splitter that keeps character offsets.

Rules
-----
* A sentence ends at ``.``, ``!`` or ``?`` (optionally repeated and optionally
  followed by closing quotes or brackets) when whitespace or the end of the
  block follows.
* Blank lines always end a sentence, and so does a newline followed by a list
  marker (``-``, ``*``, ``•``, ``1.``, ``1)``).
* A period does not end a sentence after a known abbreviation (``Mr.``,
  ``e.g.``, ...), after a single capital letter (initials such as ``J.``), or
  when the next word starts with a lowercase letter.

Known weaknesses
----------------
* **Abbreviations:** only a short built-in list is recognised. An unlisted
  abbreviation followed by a capitalised word (``Acme Inc. Today...``) is split
  wrongly; one that really ends a sentence (``... and so on, etc. Then``) is
  *not* split.
* **Quotes:** a sentence inside quotes that ends with ``?`` or ``!`` and is
  followed by a lowercase continuation (``"Why?" she asked.``) stays joined,
  which is usually right; but nested or unbalanced quotes are not tracked.
* **Lists:** list items without final punctuation are split only when they
  start on a new line with a recognised marker. Items written inline
  (``a) foo b) bar``) stay in one sentence.
* **Hard-wrapped text:** single newlines are treated as spaces, so a heading
  without punctuation directly above a paragraph is merged into its first
  sentence.
* **Non-English text:** rules are tuned for English punctuation only.
"""

from __future__ import annotations

import re

from grammar_agent.models import Sentence

ABBREVIATIONS = frozenset(
    {
        "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc", "e.g", "i.e",
        "approx", "fig", "no", "dept", "est", "inc", "ltd", "co", "mt", "a.m", "p.m",
    }
)  # fmt: skip

# Closing quotes/brackets that may follow a terminator: " ' ) ] and curly quotes.
_CLOSERS = "\"')]" + chr(0x201D) + chr(0x2019)
_TERMINATOR = re.compile(r"[.!?]+[" + re.escape(_CLOSERS) + r"]*(?=\s|$)")
_BLOCK_BREAK = re.compile(r"\n[ \t]*\n\s*|\n(?=[ \t]*(?:[-*\u2022]|\d+[.)])\s)")
_WORD_BEFORE = re.compile(r"([A-Za-z][A-Za-z.]*)$")


def _blocks(text: str) -> list[tuple[int, int]]:
    """Split ``text`` into (start, end) blocks at paragraph and list breaks."""
    blocks: list[tuple[int, int]] = []
    pos = 0
    for m in _BLOCK_BREAK.finditer(text):
        blocks.append((pos, m.start()))
        pos = m.end()
    blocks.append((pos, len(text)))
    return blocks


def _is_abbreviation(text: str, block_start: int, dot_pos: int) -> bool:
    m = _WORD_BEFORE.search(text, block_start, dot_pos)
    if m is None:
        return False
    word = m.group(1)
    if len(word) == 1 and word.isupper():  # an initial, e.g. "J. R. R. Tolkien"
        return True
    return word.lower() in ABBREVIATIONS


def _next_char(text: str, pos: int, end: int) -> str | None:
    while pos < end and text[pos].isspace():
        pos += 1
    return text[pos] if pos < end else None


def split_sentences(text: str) -> list[Sentence]:
    """Return the sentences in ``text`` with their offsets, in order."""
    spans: list[tuple[int, int]] = []
    for block_start, block_end in _blocks(text):
        pos = block_start
        for m in _TERMINATOR.finditer(text, block_start, block_end):
            terminator = text[m.start() : m.end()].rstrip(_CLOSERS)
            if terminator == "." and _is_abbreviation(text, block_start, m.start()):
                continue
            nxt = _next_char(text, m.end(), block_end)
            if nxt is not None and nxt.islower():
                continue
            spans.append((pos, m.end()))
            pos = m.end()
        spans.append((pos, block_end))

    sentences: list[Sentence] = []
    for start, end in spans:
        chunk = text[start:end]
        stripped = chunk.strip()
        if not stripped:
            continue
        lead = len(chunk) - len(chunk.lstrip())
        s = start + lead
        sentences.append(
            Sentence(index=len(sentences) + 1, text=stripped, start=s, end=s + len(stripped))
        )
    return sentences
