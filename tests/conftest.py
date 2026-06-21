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


@pytest_asyncio.fixture
async def engine() -> AsyncIterator:
    """Create a fresh schema on a per-test engine.

    The engine is function-scoped on purpose: it guarantees each test and its
    background tasks use the same event loop as the connections they open. A
    session-scoped engine creates asyncpg connections on one loop and hands them
    to tests running on other loops (pytest-asyncio uses a per-test loop by
    default), which surfaces as the asyncpg error
    "cannot perform operation: another operation is in progress". Recreating the
    schema per test also makes every test fully isolated without manual TRUNCATE.
    """
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
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return _get_session
