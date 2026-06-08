"""Semantic retrieval and prompt-context assembly."""
from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings, get_settings
from app.repositories.chunks import ChunkRepository, ScoredChunk
from app.services.chunking import estimate_tokens
from app.services.embeddings import EmbeddingClient


@dataclass(frozen=True, slots=True)
class RetrievedContext:
    """The assembled prompt context and the chunks it was built from."""

    text: str
    chunks: list[ScoredChunk]


class RetrievalService:
    """Embed a query, find similar chunks and build a bounded context block."""

    def __init__(
        self,
        chunk_repository: ChunkRepository,
        embedding_client: EmbeddingClient,
        settings: Settings | None = None,
    ) -> None:
        self._chunks = chunk_repository
        self._embeddings = embedding_client
        self._settings = settings or get_settings()

    async def retrieve(self, query: str, *, top_k: int | None = None) -> list[ScoredChunk]:
        """Return the most relevant chunks for ``query``."""
        query = query.strip()
        if not query:
            return []
        embedding = await self._embeddings.embed_query(query)
        limit = top_k or self._settings.retrieval_top_k
        return await self._chunks.search(embedding, top_k=limit)

    def build_context(self, chunks: list[ScoredChunk]) -> RetrievedContext:
        """Concatenate chunks into a numbered context within the token budget.

        Chunks are added in relevance order until the configured token budget is
        reached, so the most relevant evidence is always included first.
        """
        budget = self._settings.max_context_tokens
        used = 0
        selected: list[ScoredChunk] = []
        blocks: list[str] = []

        for position, chunk in enumerate(chunks, start=1):
            cost = estimate_tokens(chunk.content)
            if selected and used + cost > budget:
                break
            selected.append(chunk)
            blocks.append(
                f"[{position}] Source: {chunk.document_filename} "
                f"(fragment #{chunk.chunk_index})\n{chunk.content}"
            )
            used += cost

        return RetrievedContext(text="\n\n".join(blocks), chunks=selected)
