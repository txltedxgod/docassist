"""Document upload, listing, download and deletion endpoints."""
from __future__ import annotations

import os
from http import HTTPStatus

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import FileResponse

from app.api.deps import DocumentRepoDep, QueueDep, StorageDep
from app.core.config import get_settings
from app.core.exceptions import (
    DocumentNotFoundError,
    FileTooLargeError,
    UnsupportedFileTypeError,
)
from app.core.logging import get_logger
from app.schemas.document import DocumentListResponse, DocumentOut

router = APIRouter(prefix="/documents", tags=["documents"])
_logger = get_logger(__name__)


def _extension_of(filename: str) -> str:
    return os.path.splitext(filename)[1].lower().lstrip(".")


@router.post(
    "",
    response_model=DocumentOut,
    status_code=HTTPStatus.ACCEPTED,
    summary="Upload a document for asynchronous ingestion",
)
async def upload_document(
    documents: DocumentRepoDep,
    storage: StorageDep,
    queue: QueueDep,
    file: UploadFile = File(...),
) -> DocumentOut:
    """Validate and store an uploaded file, then queue it for ingestion.

    Returns ``202 Accepted`` immediately; ingestion happens in the background.
    """
    settings = get_settings()
    filename = file.filename or "untitled"
    extension = _extension_of(filename)
    if extension not in settings.allowed_extensions:
        raise UnsupportedFileTypeError(
            f"Unsupported '.{extension}'. Allowed: "
            f"{', '.join(sorted(settings.allowed_extensions))}."
        )

    data = await file.read()
    if not data:
        raise UnsupportedFileTypeError("Uploaded file is empty.")
    if len(data) > settings.upload_size_limit:
        raise FileTooLargeError(
            f"File is {len(data)} bytes; limit is {settings.upload_size_limit} bytes."
        )

    storage_key = storage.save(data, extension=extension)
    document = await documents.create(
        filename=filename,
        content_type=file.content_type or "application/octet-stream",
        extension=extension,
        size_bytes=len(data),
        storage_path=storage_key,
    )
    await documents._session.commit()  # noqa: SLF001 - commit the request unit of work
    await queue.enqueue(document.id)
    _logger.info("document_uploaded", document_id=document.id, filename=filename)
    return DocumentOut.model_validate(document)


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    documents: DocumentRepoDep, limit: int = 100, offset: int = 0
) -> DocumentListResponse:
    """List uploaded documents, newest first."""
    items = await documents.list(limit=min(limit, 200), offset=max(offset, 0))
    return DocumentListResponse(
        items=[DocumentOut.model_validate(item) for item in items], count=len(items)
    )


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(document_id: int, documents: DocumentRepoDep) -> DocumentOut:
    """Return a single document by id."""
    document = await documents.get(document_id)
    if document is None:
        raise DocumentNotFoundError()
    return DocumentOut.model_validate(document)


@router.get("/{document_id}/download")
async def download_document(
    document_id: int, documents: DocumentRepoDep, storage: StorageDep
) -> FileResponse:
    """Stream the original uploaded file back to the client."""
    document = await documents.get(document_id)
    if document is None:
        raise DocumentNotFoundError()
    path = storage.resolve(document.storage_path)
    if not path.exists():
        raise DocumentNotFoundError("The stored file is no longer available.")
    return FileResponse(
        path, filename=document.filename, media_type=document.content_type
    )


@router.delete("/{document_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_document(
    document_id: int, documents: DocumentRepoDep, storage: StorageDep
) -> None:
    """Delete a document, its chunks (cascade) and its stored file."""
    document = await documents.get(document_id)
    if document is None:
        raise DocumentNotFoundError()
    storage_key = document.storage_path
    await documents.delete(document)
    await documents._session.commit()  # noqa: SLF001 - commit the request unit of work
    storage.delete(storage_key)
    _logger.info("document_deleted", document_id=document_id)
