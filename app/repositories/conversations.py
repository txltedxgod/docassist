"""Data-access layer for conversations and messages."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.conversation import Conversation, Message, MessageRole


class ConversationRepository:
    """CRUD operations for conversations and their messages."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, title: str) -> Conversation:
        """Create a new conversation."""
        conversation = Conversation(title=title[:512] or "New conversation")
        self._session.add(conversation)
        await self._session.flush()
        return conversation

    async def get(self, conversation_id: int) -> Conversation | None:
        """Return a conversation by id without eagerly loading messages."""
        return await self._session.get(Conversation, conversation_id)

    async def get_with_messages(self, conversation_id: int) -> Conversation | None:
        """Return a conversation with its messages eagerly loaded."""
        stmt = (
            select(Conversation)
            .where(Conversation.id == conversation_id)
            .options(selectinload(Conversation.messages))
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list(self, *, limit: int = 100, offset: int = 0) -> list[Conversation]:
        """Return conversations ordered by most recently created first."""
        stmt = (
            select(Conversation)
            .order_by(Conversation.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def recent_messages(
        self, conversation_id: int, *, limit: int
    ) -> list[Message]:
        """Return up to ``limit`` most recent messages in chronological order."""
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.id.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        messages = list(result.scalars().all())
        messages.reverse()
        return messages

    async def add_message(
        self,
        conversation_id: int,
        *,
        role: MessageRole,
        content: str,
        sources: list[dict] | None = None,
    ) -> Message:
        """Append a message to a conversation."""
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            sources=sources,
        )
        self._session.add(message)
        await self._session.flush()
        return message

    async def delete(self, conversation: Conversation) -> None:
        """Delete a conversation; messages are removed via cascade."""
        await self._session.delete(conversation)
        await self._session.flush()
