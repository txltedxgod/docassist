"""Document API schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.document import DocumentStatus


class DocumentOut(BaseModel):
    """Document representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    content_type: str
    extension: str
    size_bytes: int
    status: DocumentStatus
    num_chunks: int
    error: str | None
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    """Paginated list of documents."""

    items: list[DocumentOut]
    count: int
