"""Chat and conversation API schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.conversation import MessageRole


class ChatRequest(BaseModel):
    """Inbound chat question."""

    question: str = Field(min_length=1, max_length=8000)
    conversation_id: int | None = Field(
        default=None, description="Continue an existing conversation when provided."
    )
    stream: bool = Field(default=True, description="Stream the answer via SSE.")


class SourceOut(BaseModel):
    """A citation returned alongside an answer."""

    position: int
    document_id: int
    filename: str
    fragment: int
    score: float
    download_url: str


class ChatResponse(BaseModel):
    """Non-streaming chat answer."""

    conversation_id: int
    answer: str
    sources: list[SourceOut]


class MessageOut(BaseModel):
    """A single stored message."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    role: MessageRole
    content: str
    sources: list[SourceOut] | None
    created_at: datetime


class ConversationOut(BaseModel):
    """Conversation summary without messages."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationDetail(ConversationOut):
    """Conversation including its ordered messages."""

    messages: list[MessageOut]


class ConversationListResponse(BaseModel):
    """Paginated list of conversations."""

    items: list[ConversationOut]
    count: int
