"""Conversation history endpoints."""
from __future__ import annotations

from http import HTTPStatus

from fastapi import APIRouter, Response

from app.api.deps import ConversationRepoDep
from app.core.exceptions import ConversationNotFoundError
from app.schemas.chat import (
    ConversationDetail,
    ConversationListResponse,
    ConversationOut,
    MessageOut,
)

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    conversations: ConversationRepoDep, limit: int = 100, offset: int = 0
) -> ConversationListResponse:
    """List conversations, newest first."""
    items = await conversations.list(limit=min(limit, 200), offset=max(offset, 0))
    return ConversationListResponse(
        items=[ConversationOut.model_validate(item) for item in items],
        count=len(items),
    )


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: int, conversations: ConversationRepoDep
) -> ConversationDetail:
    """Return a conversation with its full message history."""
    conversation = await conversations.get_with_messages(conversation_id)
    if conversation is None:
        raise ConversationNotFoundError()
    return ConversationDetail(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=[MessageOut.model_validate(message) for message in conversation.messages],
    )


@router.delete("/{conversation_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_conversation(
    conversation_id: int, conversations: ConversationRepoDep
) -> Response:
    """Delete a conversation and its messages (cascade)."""
    conversation = await conversations.get(conversation_id)
    if conversation is None:
        raise ConversationNotFoundError()
    await conversations.delete(conversation)
    return Response(status_code=HTTPStatus.NO_CONTENT)
