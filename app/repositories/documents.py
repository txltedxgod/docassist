"""Data-access layer for documents."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentStatus


class DocumentRepository:
    """CRUD operations for :class:`Document` rows."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        filename: str,
        content_type: str,
        extension: str,
        size_bytes: int,
        storage_path: str,
    ) -> Document:
        """Insert a new document in the ``PENDING`` state."""
        document = Document(
            filename=filename,
            content_type=content_type,
            extension=extension,
            size_bytes=size_bytes,
            storage_path=storage_path,
            status=DocumentStatus.PENDING,
        )
        self._session.add(document)
        await self._session.flush()
        return document

    async def get(self, document_id: int) -> Document | None:
        """Return a document by id, or ``None`` if it does not exist."""
        return await self._session.get(Document, document_id)

    async def list(self, *, limit: int = 100, offset: int = 0) -> list[Document]:
        """Return documents ordered by most recently created first."""
        stmt = (
            select(Document)
            .order_by(Document.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def set_status(
        self,
        document: Document,
        status: DocumentStatus,
        *,
        num_chunks: int | None = None,
        error: str | None = None,
    ) -> Document:
        """Update the lifecycle status (and optional metadata) of a document."""
        document.status = status
        if num_chunks is not None:
            document.num_chunks = num_chunks
        document.error = error
        await self._session.flush()
        return document

    async def delete(self, document: Document) -> None:
        """Delete a document; chunks are removed via ``ON DELETE CASCADE``."""
        await self._session.delete(document)
        await self._session.flush()
