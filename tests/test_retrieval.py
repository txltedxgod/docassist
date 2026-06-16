"""Tests for semantic search and context assembly against the test database."""
from __future__ import annotations

import pytest

from app.models.document import Document, DocumentStatus
from app.repositories.chunks import ChunkRepository
from app.services.retrieval import RetrievalService

pytestmark = pytest.mark.asyncio


async def _seed_document(session, embedding_client, *, filename: str, chunks: list[str]):
    document = Document(
        filename=filename,
        content_type="text/plain",
        extension="txt",
        size_bytes=100,
        storage_path=f"{filename}.key",
        status=DocumentStatus.READY,
        num_chunks=len(chunks),
    )
    session.add(document)
    await session.flush()
    embeddings = await embedding_client.embed_texts(chunks)
    await ChunkRepository(session).add_many(
        document.id,
        [(i, content, len(content.split()), emb) for i, (content, emb) in enumerate(zip(chunks, embeddings))],
    )
    await session.commit()
    return document


async def test_search_ranks_relevant_chunk_first(session_factory, embedding_client) -> None:
    async with session_factory() as session:
        await _seed_document(
            session,
            embedding_client,
            filename="finance.txt",
            chunks=[
                "quarterly revenue grew due to strong enterprise sales",
                "the office cafeteria menu changes every monday",
            ],
        )
        service = RetrievalService(ChunkRepository(session), embedding_client)
        results = await service.retrieve("how did revenue grow this quarter", top_k=2)

    assert results
    assert "revenue" in results[0].content
    assert results[0].score >= results[-1].score


async def test_build_context_respects_token_budget(session_factory, embedding_client) -> None:
    async with session_factory() as session:
        await _seed_document(
            session,
            embedding_client,
            filename="big.txt",
            chunks=[" ".join(["alpha"] * 100), " ".join(["beta"] * 100)],
        )
        service = RetrievalService(ChunkRepository(session), embedding_client)
        service._settings.max_context_tokens = 100  # force truncation after one chunk
        results = await service.retrieve("alpha", top_k=5)
        context = service.build_context(results)

    assert len(context.chunks) == 1
    assert context.text.startswith("[1] Source: big.txt")


async def test_search_ignores_non_ready_documents(session_factory, embedding_client) -> None:
    async with session_factory() as session:
        doc = await _seed_document(
            session, embedding_client, filename="draft.txt", chunks=["pending content here"]
        )
        doc.status = DocumentStatus.PROCESSING
        await session.commit()
        service = RetrievalService(ChunkRepository(session), embedding_client)
        results = await service.retrieve("pending content", top_k=5)

    assert results == []
