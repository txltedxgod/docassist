"""Token-aware text chunking.

The pipeline avoids a hard dependency on a model-specific tokenizer: counting
whitespace-delimited words is a stable, deterministic proxy for token budgeting
and keeps chunking testable without network access. Splitting prefers paragraph
and sentence boundaries so chunks stay semantically coherent.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_WORD_RE = re.compile(r"\S+")
_PARAGRAPH_RE = re.compile(r"\n\s*\n")
_SENTENCE_RE = re.compile(r"(?<=[.!?\u2026])\s+")


@dataclass(frozen=True, slots=True)
class TextChunk:
    """A contiguous slice of source text and its token estimate."""

    index: int
    content: str
    token_count: int


def estimate_tokens(text: str) -> int:
    """Estimate the token count of ``text`` using whitespace word counting."""
    return len(_WORD_RE.findall(text))


def normalize_text(text: str) -> str:
    """Collapse excessive whitespace while preserving paragraph breaks."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _split_units(text: str) -> list[str]:
    """Split text into the smallest units used to assemble chunks.

    Paragraphs are preferred; long paragraphs fall back to sentence splitting so
    a single unit never dwarfs the target chunk size.
    """
    units: list[str] = []
    for paragraph in _PARAGRAPH_RE.split(text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        units.extend(s for s in _SENTENCE_RE.split(paragraph) if s.strip())
    return units


def _overlap_tail(words: list[str], overlap: int) -> list[str]:
    """Return the trailing ``overlap`` words used to seed the next chunk."""
    if overlap <= 0:
        return []
    return words[-overlap:]


def chunk_text(
    text: str,
    *,
    chunk_size: int = 800,
    overlap: int = 100,
) -> list[TextChunk]:
    """Split ``text`` into overlapping, token-budgeted chunks.

    Args:
        text: Raw document text.
        chunk_size: Target maximum tokens per chunk.
        overlap: Number of trailing tokens carried into the next chunk.

    Returns:
        Ordered list of :class:`TextChunk`. Empty input yields an empty list.

    Raises:
        ValueError: If ``chunk_size`` <= 0 or ``overlap`` is out of ``[0, chunk_size)``.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if not 0 <= overlap < chunk_size:
        raise ValueError("overlap must satisfy 0 <= overlap < chunk_size")

    normalized = normalize_text(text)
    if not normalized:
        return []

    chunks: list[TextChunk] = []
    current: list[str] = []

    def flush() -> None:
        if not current:
            return
        content = " ".join(current).strip()
        chunks.append(TextChunk(len(chunks), content, len(current)))

    for unit in _split_units(normalized):
        unit_words = unit.split()
        if not unit_words:
            continue

        # A single oversized unit is hard-split to respect the token budget.
        if len(unit_words) > chunk_size:
            flush()
            current = []
            for start in range(0, len(unit_words), chunk_size - overlap):
                window = unit_words[start : start + chunk_size]
                chunks.append(
                    TextChunk(len(chunks), " ".join(window), len(window))
                )
            continue

        if len(current) + len(unit_words) > chunk_size:
            tail = _overlap_tail(current, overlap)
            flush()
            current = [*tail, *unit_words]
        else:
            current.extend(unit_words)

    flush()
    return chunks
