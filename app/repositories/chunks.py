"""Data-access layer for chunks and vector similarity search."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus


@dataclass(frozen=True, slots=True)
class ScoredChunk:
    """A retrieved chunk enriched with its document context and score."""

    chunk_id: int
    document_id: int
    document_filename: str
    chunk_index: int
    content: str
    score: float


class ChunkRepository:
    """Persistence and retrieval for :class:`Chunk` rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add_many(
        self,
        document_id: int,
        chunks: list[tuple[int, str, int, list[float]]],
    ) -> None:
        """Bulk-insert chunks.

        Each tuple is ``(chunk_index, content, token_count, embedding)``.
        """
        self._session.add_all(
            [
                Chunk(
                    document_id=document_id,
                    chunk_index=index,
                    content=content,
                    token_count=token_count,
                    embedding=embedding,
                )
                for index, content, token_count, embedding in chunks
            ]
        )
        await self._session.flush()

    async def search(
        self,
        query_embedding: list[float],
        *,
        top_k: int,
    ) -> list[ScoredChunk]:
        """Return the ``top_k`` most similar ready-document chunks.

        Ranking uses pgvector's cosine distance operator; the reported score is
        ``1 - distance`` so that larger means more relevant.
        """
        distance = Chunk.embedding.cosine_distance(query_embedding).label("distance")
        stmt = (
            select(
                Chunk.id,
                Chunk.document_id,
                Chunk.chunk_index,
                Chunk.content,
                Document.filename,
                distance,
            )
            .join(Document, Document.id == Chunk.document_id)
            .where(Document.status == DocumentStatus.READY)
            .order_by(distance)
            .limit(top_k)
        )
        result = await self._session.execute(stmt)
        return [
            ScoredChunk(
                chunk_id=row.id,
                document_id=row.document_id,
                document_filename=row.filename,
                chunk_index=row.chunk_index,
                content=row.content,
                score=round(1.0 - float(row.distance), 6),
            )
            for row in result.all()
        ]
