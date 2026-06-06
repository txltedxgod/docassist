"""LLM client for an OpenAI-compatible chat-completions endpoint.

Provides both buffered and streaming (SSE-style) completions. Transient network
failures while establishing the request are retried with backoff; once tokens
start streaming we do not retry, to avoid emitting duplicated partial answers.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx

from app.core.config import Settings, get_settings
from app.core.exceptions import LLMServiceError
from app.core.logging import get_logger
from app.core.retry import retry_async

_logger = get_logger(__name__)
_RETRYABLE = (httpx.TransportError, httpx.HTTPStatusError)

ChatMessage = dict[str, str]


class LLMClient:
    """Thin async wrapper over the chat-completions API."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def complete(self, messages: list[ChatMessage], *, temperature: float = 0.2) -> str:
        """Return a full completion for ``messages``.

        Raises:
            LLMServiceError: On malformed responses or exhausted retries.
        """

        async def _call() -> str:
            async with self._client() as client:
                response = await client.post(
                    "/chat/completions",
                    json=self._payload(messages, temperature, stream=False),
                )
                response.raise_for_status()
                return self._parse_completion(response.json())

        try:
            return await retry_async(
                _call,
                retry_on=_RETRYABLE,
                max_attempts=self._settings.llm_max_retries,
                base_delay=self._settings.llm_backoff_base,
                max_delay=self._settings.llm_backoff_max,
                operation="chat.completion",
            )
        except _RETRYABLE as exc:
            raise LLMServiceError(f"LLM request failed: {exc}") from exc

    async def stream(
        self, messages: list[ChatMessage], *, temperature: float = 0.2
    ) -> AsyncIterator[str]:
        """Yield completion tokens as they arrive from the API.

        The initial connection is retried; streaming itself is not.
        """

        async def _open() -> httpx.Response:
            client = self._client()
            request = client.build_request(
                "POST",
                "/chat/completions",
                json=self._payload(messages, temperature, stream=True),
            )
            response = await client.send(request, stream=True)
            response.raise_for_status()
            response.extensions["_client"] = client  # keep client alive for the stream
            return response

        try:
            response = await retry_async(
                _open,
                retry_on=_RETRYABLE,
                max_attempts=self._settings.llm_max_retries,
                base_delay=self._settings.llm_backoff_base,
                max_delay=self._settings.llm_backoff_max,
                operation="chat.completion.stream",
            )
        except _RETRYABLE as exc:
            raise LLMServiceError(f"LLM streaming request failed: {exc}") from exc

        client = response.extensions["_client"]
        try:
            async for line in response.aiter_lines():
                token = self._parse_stream_line(line)
                if token:
                    yield token
        except httpx.HTTPError as exc:
            raise LLMServiceError(f"LLM stream interrupted: {exc}") from exc
        finally:
            await response.aclose()
            await client.aclose()

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._settings.openai_base_url,
            timeout=self._settings.request_timeout,
            headers={"Authorization": f"Bearer {self._settings.openai_api_key}"},
        )

    def _payload(
        self, messages: list[ChatMessage], temperature: float, *, stream: bool
    ) -> dict:
        return {
            "model": self._settings.llm_model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
        }

    def _parse_completion(self, payload: dict) -> str:
        try:
            return payload["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMServiceError("Malformed completion response.") from exc

    def _parse_stream_line(self, line: str) -> str:
        """Extract a token from a single SSE ``data:`` line, if present."""
        line = line.strip()
        if not line or not line.startswith("data:"):
            return ""
        data = line[len("data:") :].strip()
        if data == "[DONE]":
            return ""
        try:
            chunk = json.loads(data)
            return chunk["choices"][0]["delta"].get("content", "") or ""
        except (json.JSONDecodeError, KeyError, IndexError, TypeError):
            # A malformed keep-alive frame should not kill the whole stream.
            return ""
