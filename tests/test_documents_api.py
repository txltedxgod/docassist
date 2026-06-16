"""Tests for document upload validation and error handling."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.asyncio


async def test_rejects_unsupported_file_type(client) -> None:
    response = await client.post(
        "/documents",
        files={"file": ("notes.exe", b"binary", "application/octet-stream")},
    )
    assert response.status_code == 415
    body = response.json()
    assert body["code"] == "unsupported_file_type"


async def test_rejects_empty_file(client) -> None:
    response = await client.post(
        "/documents", files={"file": ("empty.txt", b"", "text/plain")}
    )
    assert response.status_code == 415


async def test_missing_document_returns_404(client) -> None:
    response = await client.get("/documents/999999")
    assert response.status_code == 404
    assert response.json()["code"] == "document_not_found"


async def test_upload_then_list_and_delete(client) -> None:
    upload = await client.post(
        "/documents",
        files={"file": ("intro.md", b"# Title\n\nDocAssist ingests documents.", "text/markdown")},
    )
    assert upload.status_code == 202
    document_id = upload.json()["id"]

    listing = await client.get("/documents")
    assert listing.status_code == 200
    assert any(item["id"] == document_id for item in listing.json()["items"])

    deleted = await client.delete(f"/documents/{document_id}")
    assert deleted.status_code == 204

    missing = await client.get(f"/documents/{document_id}")
    assert missing.status_code == 404
