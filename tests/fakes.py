"""Deterministic test doubles for the external LLM and embedding services.

These are intentionally not mocks-of-everything: they implement the same public
interface as the real clients so services, repositories and the database under
test exercise real code paths. Only the network boundary is replaced.
"""
from __future__ import annotations

import hashlib
import math
from collections.abc import AsyncIterator


class FakeEmbeddingClient:
    """Hash-based embedding client producing stable, normalised vectors."""

    def __init__(self, dim: int) -> None:
        self._dim = dim

    def _vector(self, text: str) -> list[float]:
        # Seed a small set of dimensions from the token hashes so semantically
        # similar strings (shared words) land close together in cosine space.
        vec = [0.0] * self._dim
        for token in text.lower().split():
            digest = hashlib.sha256(token.encode()).digest()
            idx = int.from_bytes(digest[:4], "big") % self._dim
            vec[idx] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


class FakeLLMClient:
    """LLM stub that echoes retrieved context so answers are assertable."""

    def __init__(self, reply: str = "Based on the context [1], here is the answer.") -> None:
        self._reply = reply

    async def complete(self, messages: list[dict], *, temperature: float = 0.2) -> str:
        return self._reply

    async def stream(
        self, messages: list[dict], *, temperature: float = 0.2
    ) -> AsyncIterator[str]:
        for word in self._reply.split(" "):
            yield word + " "
