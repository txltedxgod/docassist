"""aiogram message handlers backing the Telegram interface."""
from __future__ import annotations

import httpx
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Document as TgDocument
from aiogram.types import Message

from app.core.config import get_settings
from app.core.logging import get_logger
from bot.client import ApiClient

router = Router()
_logger = get_logger(__name__)

# Per-chat conversation ids so each Telegram chat keeps its own dialogue thread.
_conversations: dict[int, int] = {}


def _client() -> ApiClient:
    settings = get_settings()
    return ApiClient(settings.api_base_url, timeout=settings.telegram_request_timeout)


@router.message(Command("start", "help"))
async def handle_start(message: Message) -> None:
    """Greet the user and explain how to use the bot."""
    await message.answer(
        "DocAssist bot\n\n"
        "Send me a document (PDF, DOCX, TXT, MD) and I will ingest it. "
        "Then just ask questions and I will answer from your documents with "
        "sources.\n\n"
        "Commands:\n"
        "/reset - start a new conversation"
    )


@router.message(Command("reset"))
async def handle_reset(message: Message) -> None:
    """Forget the current conversation for this chat."""
    _conversations.pop(message.chat.id, None)
    await message.answer("Conversation reset. Ask me anything.")


@router.message(F.document)
async def handle_document(message: Message) -> None:
    """Download an attached document and forward it to the ingestion API."""
    document: TgDocument = message.document
    assert document is not None  # guarded by the F.document filter

    settings = get_settings()
    if document.file_size and document.file_size > settings.upload_size_limit:
        await message.answer("That file is too large.")
        return

    buffer = await message.bot.download(document.file_id)
    if buffer is None:
        await message.answer("Could not download that file from Telegram.")
        return
    content = buffer.read()

    try:
        result = await _client().upload(
            filename=document.file_name or "document",
            content=content,
            content_type=document.mime_type or "application/octet-stream",
        )
    except httpx.HTTPStatusError as exc:
        detail = exc.response.json().get("message", exc.response.text)
        await message.answer(f"Upload rejected: {detail}")
        return
    except httpx.HTTPError as exc:
        _logger.warning("bot_upload_failed", error=str(exc))
        await message.answer("The API is unreachable right now. Try again later.")
        return

    await message.answer(
        f"Got '{result['filename']}'. Ingesting it now - ask a question in a moment."
    )


@router.message(F.text)
async def handle_question(message: Message) -> None:
    """Answer a free-text question via the chat API."""
    question = (message.text or "").strip()
    if not question:
        return

    conversation_id = _conversations.get(message.chat.id)
    await message.bot.send_chat_action(message.chat.id, "typing")
    try:
        answer = await _client().ask(question, conversation_id=conversation_id)
    except httpx.HTTPError as exc:
        _logger.warning("bot_chat_failed", error=str(exc))
        await message.answer("I could not reach the assistant. Try again later.")
        return

    _conversations[message.chat.id] = answer.conversation_id
    await message.answer(_format_answer(answer.answer, answer.sources))


def _format_answer(answer: str, sources: list[dict]) -> str:
    """Render an answer plus a compact, clickable source list."""
    if not sources:
        return answer or "I could not find an answer in your documents."
    lines = [answer, "", "Sources:"]
    lines.extend(
        f"[{s['position']}] {s['filename']} #{s['fragment']} - {s['download_url']}"
        for s in sources
    )
    return "\n".join(lines)
