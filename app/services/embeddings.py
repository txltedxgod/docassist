"""Embedding client for an OpenAI-compatible embeddings endpoint."""
from __future__ import annotations

import httpx

from app.core.config import Settings, get_settings
from app.core.exceptions import EmbeddingServiceError
from app.core.logging import get_logger
from app.core.retry import retry_async

_logger = get_logger(__name__)
_RETRYABLE = (httpx.TransportError, httpx.HTTPStatusError)


class EmbeddingClient:
    """Generate embeddings via the ``/embeddings`` API with retries."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts, preserving input order.

        Raises:
            EmbeddingServiceError: If the service keeps failing after retries or
                returns a malformed payload.
        """
        if not texts:
            return []

        async def _call() -> list[list[float]]:
            async with httpx.AsyncClient(
                base_url=self._settings.openai_base_url,
                timeout=self._settings.request_timeout,
                headers=self._auth_headers(),
            ) as client:
                response = await client.post(
                    "/embeddings",
                    json={"model": self._settings.embedding_model, "input": texts},
                )
                response.raise_for_status()
                return self._parse(response.json())

        try:
            return await retry_async(
                _call,
                retry_on=_RETRYABLE,
                max_attempts=self._settings.llm_max_retries,
                base_delay=self._settings.llm_backoff_base,
                max_delay=self._settings.llm_backoff_max,
                operation="embeddings",
            )
        except _RETRYABLE as exc:
            raise EmbeddingServiceError(f"Embedding request failed: {exc}") from exc

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query string."""
        vectors = await self.embed_texts([text])
        return vectors[0]

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._settings.openai_api_key}"}

    def _parse(self, payload: dict) -> list[list[float]]:
        try:
            items = sorted(payload["data"], key=lambda item: item["index"])
            vectors = [item["embedding"] for item in items]
        except (KeyError, TypeError) as exc:
            raise EmbeddingServiceError("Malformed embedding response.") from exc
        expected = self._settings.embedding_dim
        if any(len(vector) != expected for vector in vectors):
            raise EmbeddingServiceError(
                f"Embedding dimension mismatch; expected {expected}."
            )
        return vectors
