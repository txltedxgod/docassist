"""Document ingestion pipeline: extract -> chunk -> embed -> persist."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.exceptions import AppError, DocumentNotFoundError, EmptyDocumentError
from app.core.logging import get_logger
from app.models.document import DocumentStatus
from app.repositories.chunks import ChunkRepository
from app.repositories.documents import DocumentRepository
from app.services.chunking import chunk_text
from app.services.embeddings import EmbeddingClient
from app.services.extraction import extract_text
from app.services.storage import FileStorage

_logger = get_logger(__name__)


class IngestionService:
    """Run the full ingestion pipeline for a single document."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        storage: FileStorage,
        embedding_client: EmbeddingClient,
        settings: Settings | None = None,
    ) -> None:
        self._session = session
        self._documents = DocumentRepository(session)
        self._chunks = ChunkRepository(session)
        self._storage = storage
        self._embeddings = embedding_client
        self._settings = settings or get_settings()

    async def run(self, document_id: int) -> None:
        """Process a pending document, updating its status as it progresses.

        Expected failures (empty/corrupt file, upstream errors) are recorded on
        the document as ``FAILED`` with a message rather than crashing the worker.
        """
        document = await self._documents.get(document_id)
        if document is None:
            raise DocumentNotFoundError(f"Document {document_id} disappeared.")

        await self._documents.set_status(document, DocumentStatus.PROCESSING)
        await self._session.commit()
        _logger.info("ingestion_started", document_id=document_id, filename=document.filename)

        try:
            text = extract_text(
                extension=document.extension,
                data=self._storage.read(document.storage_path),
            )
            chunks = chunk_text(
                text,
                chunk_size=self._settings.chunk_size_tokens,
                overlap=self._settings.chunk_overlap_tokens,
            )
            if not chunks:
                raise EmptyDocumentError()

            embeddings = await self._embeddings.embed_texts([c.content for c in chunks])
            await self._chunks.add_many(
                document_id,
                [
                    (chunk.index, chunk.content, chunk.token_count, embedding)
                    for chunk, embedding in zip(chunks, embeddings, strict=True)
                ],
            )
            await self._documents.set_status(
                document, DocumentStatus.READY, num_chunks=len(chunks)
            )
            await self._session.commit()
            _logger.info("ingestion_completed", document_id=document_id, chunks=len(chunks))
        except AppError as exc:
            await self._fail(document_id, exc.message)
            _logger.warning("ingestion_failed", document_id=document_id, error=exc.message)
        except Exception as exc:  # noqa: BLE001 - persist unexpected errors, keep worker alive
            await self._fail(document_id, f"Unexpected error: {exc}")
            _logger.exception("ingestion_crashed", document_id=document_id)

    async def _fail(self, document_id: int, message: str) -> None:
        """Roll back partial work and mark the document as failed."""
        await self._session.rollback()
        document = await self._documents.get(document_id)
        if document is None:
            return
        await self._documents.set_status(
            document, DocumentStatus.FAILED, num_chunks=0, error=message
        )
        await self._session.commit()
