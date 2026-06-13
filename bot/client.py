"""Async HTTP client used by the Telegram bot to talk to the API."""
from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(frozen=True, slots=True)
class ChatAnswer:
    """A buffered chat answer with its sources."""

    conversation_id: int
    answer: str
    sources: list[dict]


class ApiClient:
    """Thin wrapper over the DocAssist REST API."""

    def __init__(self, base_url: str, *, timeout: float = 120.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    async def upload(self, *, filename: str, content: bytes, content_type: str) -> dict:
        """Upload a document fetched from Telegram."""
        async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
            response = await client.post(
                "/documents",
                files={"file": (filename, content, content_type)},
            )
            response.raise_for_status()
            return response.json()

    async def ask(self, question: str, *, conversation_id: int | None) -> ChatAnswer:
        """Ask a question using the buffered (non-streaming) endpoint."""
        async with httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout) as client:
            response = await client.post(
                "/chat",
                json={
                    "question": question,
                    "conversation_id": conversation_id,
                    "stream": False,
                },
            )
            response.raise_for_status()
            data = response.json()
        return ChatAnswer(
            conversation_id=data["conversation_id"],
            answer=data["answer"],
            sources=data["sources"],
        )
