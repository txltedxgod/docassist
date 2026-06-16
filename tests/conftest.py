"""Shared pytest fixtures: test database, app wiring and HTTP client.

The suite talks to a real PostgreSQL + pgvector instance (see ``TEST_DATABASE_URL``
or the default) so vector search and cascading deletes are genuinely exercised.
Only the LLM and embedding network boundaries are replaced by deterministic
fakes from ``tests.fakes``.
"""
from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.session import get_session
from app.main import create_app
from app.models import Base
from app.services.queue import IngestionQueue
from app.services.storage import FileStorage
from tests.fakes import FakeEmbeddingClient, FakeLLMClient

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://docassist:docassist@localhost:5432/docassist_test",
)


@pytest_asyncio.fixture(scope="session")
async def engine() -> AsyncIterator:
    """Create the schema once for the whole test session."""
    engine = create_async_engine(TEST_DATABASE_URL, future=True)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(engine) -> async_sessionmaker:
    """Return a session factory bound to the test engine."""
    return async_sessionmaker(bind=engine, expire_on_commit=False)


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables(engine) -> AsyncIterator[None]:
    """Truncate all tables between tests for isolation."""
    yield
    async with engine.begin() as conn:
        await conn.execute(
            text("TRUNCATE documents, chunks, conversations, messages RESTART IDENTITY CASCADE")
        )


@pytest.fixture
def embedding_client() -> FakeEmbeddingClient:
    return FakeEmbeddingClient(get_settings().embedding_dim)


@pytest.fixture
def llm_client() -> FakeLLMClient:
    return FakeLLMClient()


@pytest_asyncio.fixture
async def client(
    engine, session_factory, embedding_client, llm_client, tmp_path
) -> AsyncIterator[AsyncClient]:
    """Yield an HTTP client wired to the app with fakes and the test DB."""
    app = create_app()
    storage = FileStorage(tmp_path / "storage")
    queue = IngestionQueue(
        session_factory,
        storage=storage,
        embedding_client=embedding_client,
    )

    app.dependency_overrides[get_session] = _session_override(session_factory)
    app.state.storage = storage
    app.state.embedding_client = embedding_client
    app.state.llm_client = llm_client
    app.state.ingestion_queue = queue

    await queue.start()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
    await queue.stop()


def _session_override(session_factory: async_sessionmaker):
    async def _get_session() -> AsyncIterator:
        async with session_factory() as session:
            yield session

    return _get_session
