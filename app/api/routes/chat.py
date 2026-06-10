"""Chat endpoint with both streaming (SSE) and buffered responses."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.deps import RAGServiceDep
from app.core.logging import get_logger
from app.schemas.chat import ChatRequest, ChatResponse, SourceOut
from app.services.rag import Source

router = APIRouter(tags=["chat"])
_logger = get_logger(__name__)


def _sse(event: str, data: object) -> str:
    """Render a single Server-Sent Event frame."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _event_stream(
    rag: RAGServiceDep, conversation_id: int, prompt: str, sources: list[Source]
) -> AsyncIterator[str]:
    """Produce the SSE event sequence: metadata -> sources -> tokens -> done."""
    yield _sse("meta", {"conversation_id": conversation_id})
    yield _sse("sources", [source.as_dict() for source in sources])
    try:
        async for token in rag.stream_answer(
            conversation_id=conversation_id, prompt=prompt, sources=sources
        ):
            yield _sse("token", {"content": token})
    except Exception as exc:  # noqa: BLE001 - surface failures inside the stream
        _logger.exception("chat_stream_failed", conversation_id=conversation_id)
        yield _sse("error", {"message": str(exc)})
        return
    yield _sse("done", {"conversation_id": conversation_id})


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, rag: RAGServiceDep):
    """Answer a question over the ingested documents.

    When ``stream`` is true (default) the response is an SSE stream emitting
    ``meta``, ``sources``, ``token`` and ``done`` events. Otherwise a single
    JSON :class:`ChatResponse` is returned.
    """
    if request.stream:
        conversation_id, prompt, sources = await rag.prepare(
            question=request.question, conversation_id=request.conversation_id
        )
        return StreamingResponse(
            _event_stream(rag, conversation_id, prompt, sources),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    conversation_id, answer, sources = await rag.answer(
        question=request.question, conversation_id=request.conversation_id
    )
    return ChatResponse(
        conversation_id=conversation_id,
        answer=answer,
        sources=[SourceOut(**source.as_dict()) for source in sources],
    )
