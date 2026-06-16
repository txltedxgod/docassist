"""Unit tests for the chunking logic (no I/O, no database)."""
from __future__ import annotations

import pytest

from app.services.chunking import chunk_text, estimate_tokens, normalize_text


def test_empty_text_returns_no_chunks() -> None:
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_short_text_is_a_single_chunk() -> None:
    chunks = chunk_text("Hello world from DocAssist.", chunk_size=50, overlap=10)
    assert len(chunks) == 1
    assert chunks[0].index == 0
    assert chunks[0].token_count == estimate_tokens(chunks[0].content)


def test_chunks_respect_size_and_overlap() -> None:
    text = " ".join(f"word{i}" for i in range(1000))
    chunks = chunk_text(text, chunk_size=200, overlap=50)

    assert len(chunks) > 1
    assert all(chunk.token_count <= 200 for chunk in chunks)
    assert [c.index for c in chunks] == list(range(len(chunks)))

    # Consecutive chunks share the configured overlap window.
    first_tail = chunks[0].content.split()[-50:]
    second_head = chunks[1].content.split()[:50]
    assert first_tail == second_head


def test_oversized_single_unit_is_hard_split() -> None:
    text = " ".join(f"token{i}" for i in range(500))  # one big paragraph, no breaks
    chunks = chunk_text(text, chunk_size=100, overlap=20)
    assert len(chunks) >= 5
    assert all(chunk.token_count <= 100 for chunk in chunks)


def test_normalize_collapses_whitespace_but_keeps_paragraphs() -> None:
    assert normalize_text("a\r\n\r\n\n\nb   c") == "a\n\nb c"


@pytest.mark.parametrize(
    ("chunk_size", "overlap"),
    [(0, 0), (100, 100), (100, 150), (50, -1)],
)
def test_invalid_parameters_raise(chunk_size: int, overlap: int) -> None:
    with pytest.raises(ValueError):
        chunk_text("some text here", chunk_size=chunk_size, overlap=overlap)
