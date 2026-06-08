"""In-process background ingestion queue.

Uploads return immediately after persisting the file; the heavy pipeline runs on
a bounded :class:`asyncio.Queue` drained by a pool of worker tasks. Each job gets
its own database session so a slow document never holds a request-scoped session.
"""
from __future__ import annotations

import asyncio

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.services.embeddings import EmbeddingClient
from app.services.ingestion import IngestionService
from app.services.storage import FileStorage

_logger = get_logger(__name__)


class IngestionQueue:
    """Bounded async work queue that ingests documents in the background."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        storage: FileStorage,
        embedding_client: EmbeddingClient,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._session_factory = session_factory
        self._storage = storage
        self._embeddings = embedding_client
        self._queue: asyncio.Queue[int] = asyncio.Queue(
            maxsize=self._settings.ingestion_queue_maxsize
        )
        self._workers: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        """Spawn the worker pool."""
        if self._workers:
            return
        for i in range(self._settings.ingestion_workers):
            self._workers.append(asyncio.create_task(self._worker(i), name=f"ingest-{i}"))
        _logger.info("ingestion_queue_started", workers=len(self._workers))

    async def stop(self) -> None:
        """Drain in-flight work and cancel the worker pool."""
        if not self._workers:
            return
        await self._queue.join()
        for task in self._workers:
            task.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        _logger.info("ingestion_queue_stopped")

    async def enqueue(self, document_id: int) -> None:
        """Schedule a document for ingestion."""
        await self._queue.put(document_id)
        _logger.info("document_enqueued", document_id=document_id, depth=self._queue.qsize())

    async def _worker(self, worker_id: int) -> None:
        while True:
            document_id = await self._queue.get()
            try:
                async with self._session_factory() as session:
                    service = IngestionService(
                        session,
                        storage=self._storage,
                        embedding_client=self._embeddings,
                        settings=self._settings,
                    )
                    await service.run(document_id)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - a single bad job must not kill the worker
                _logger.exception(
                    "ingestion_worker_error", worker_id=worker_id, document_id=document_id
                )
            finally:
                self._queue.task_done()
