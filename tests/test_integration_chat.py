"""End-to-end test: upload a document, wait for ingestion, then ask a question."""
from __future__ import annotations

import asyncio

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

_DOC = (
    b"DocAssist is a retrieval augmented generation system. "
    b"It stores document embeddings in pgvector and answers questions with sources. "
    b"The ingestion pipeline runs asynchronously in a background queue."
)


async def _wait_until_ready(client, document_id: int, *, timeout: float = 10.0) -> dict:
    """Poll the document until ingestion finishes or the timeout elapses."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        response = await client.get(f"/documents/{document_id}")
        body = response.json()
        if body["status"] in {"ready", "failed"}:
            return body
        await asyncio.sleep(0.1)
    raise AssertionError("Document did not finish ingesting in time")


async def test_full_cycle_upload_question_answer(client) -> None:
    upload = await client.post(
        "/documents",
        files={"file": ("about.txt", _DOC, "text/plain")},
    )
    assert upload.status_code == 202
    document_id = upload.json()["id"]

    document = await _wait_until_ready(client, document_id)
    assert document["status"] == "ready"
    assert document["num_chunks"] >= 1

    response = await client.post(
        "/chat",
        json={"question": "Where are embeddings stored?", "stream": False},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["answer"]
    assert body["sources"], "expected at least one cited source"
    assert body["sources"][0]["filename"] == "about.txt"
    assert body["sources"][0]["download_url"].endswith(f"/documents/{document_id}/download")

    # The conversation and its messages are persisted.
    conversation_id = body["conversation_id"]
    convo = await client.get(f"/conversations/{conversation_id}")
    assert convo.status_code == 200
    roles = [m["role"] for m in convo.json()["messages"]]
    assert roles == ["user", "assistant"]
