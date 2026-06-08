"""RAG orchestration: retrieve, build context, prompt the LLM, persist history."""
from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.models.conversation import MessageRole
from app.repositories.chunks import ScoredChunk
from app.repositories.conversations import ConversationRepository
from app.services.llm import ChatMessage, LLMClient
from app.services.retrieval import RetrievalService

_logger = get_logger(__name__)

_SYSTEM_PROMPT = (
    "You are DocAssist, a precise assistant that answers strictly from the "
    "provided context. Cite sources inline using their bracket numbers, e.g. "
    "[1]. If the context does not contain the answer, say so plainly instead of "
    "guessing."
)


@dataclass(frozen=True, slots=True)
class Source:
    """A citation pointing back at a retrieved chunk."""

    position: int
    document_id: int
    filename: str
    fragment: int
    score: float
    download_url: str

    def as_dict(self) -> dict:
        return {
            "position": self.position,
            "document_id": self.document_id,
            "filename": self.filename,
            "fragment": self.fragment,
            "score": self.score,
            "download_url": self.download_url,
        }


class RAGService:
    """Coordinate retrieval, generation and conversation persistence."""

    def __init__(
        self,
        *,
        retrieval: RetrievalService,
        llm: LLMClient,
        conversations: ConversationRepository,
        settings: Settings | None = None,
    ) -> None:
        self._retrieval = retrieval
        self._llm = llm
        self._conversations = conversations
        self._settings = settings or get_settings()

    async def prepare(
        self, *, question: str, conversation_id: int | None
    ) -> tuple[int, str, list[Source]]:
        """Resolve the conversation, retrieve context and record the question.

        Returns the conversation id, the assembled prompt and the ordered list of
        sources backing it.
        """
        conversation_id = await self._ensure_conversation(conversation_id, question)
        await self._conversations.add_message(
            conversation_id, role=MessageRole.USER, content=question
        )

        chunks = await self._retrieval.retrieve(question)
        context = self._retrieval.build_context(chunks)
        sources = self._to_sources(context.chunks)
        prompt = self._render_prompt(question, context.text)
        _logger.info(
            "rag_prepared",
            conversation_id=conversation_id,
            retrieved=len(chunks),
            used=len(sources),
        )
        return conversation_id, prompt, sources

    async def answer(self, *, question: str, conversation_id: int | None) -> tuple[int, str, list[Source]]:
        """Produce a complete (non-streaming) answer and persist it."""
        conversation_id, prompt, sources = await self.prepare(
            question=question, conversation_id=conversation_id
        )
        answer = await self._llm.complete(self._messages(prompt))
        await self._persist_answer(conversation_id, answer, sources)
        return conversation_id, answer, sources

    async def stream_answer(
        self, *, conversation_id: int, prompt: str, sources: list[Source]
    ) -> AsyncIterator[str]:
        """Stream answer tokens, persisting the full answer once complete."""
        collected: list[str] = []
        async for token in self._llm.stream(self._messages(prompt)):
            collected.append(token)
            yield token
        await self._persist_answer(conversation_id, "".join(collected), sources)

    async def _ensure_conversation(self, conversation_id: int | None, question: str) -> int:
        if conversation_id is not None:
            existing = await self._conversations.get(conversation_id)
            if existing is not None:
                return existing.id
        title = question.strip().splitlines()[0][:80] if question.strip() else "New conversation"
        conversation = await self._conversations.create(title=title)
        return conversation.id

    async def _persist_answer(
        self, conversation_id: int, answer: str, sources: list[Source]
    ) -> None:
        await self._conversations.add_message(
            conversation_id,
            role=MessageRole.ASSISTANT,
            content=answer,
            sources=[source.as_dict() for source in sources],
        )

    def _to_sources(self, chunks: list[ScoredChunk]) -> list[Source]:
        base = self._settings.public_base_url.rstrip("/")
        return [
            Source(
                position=position,
                document_id=chunk.document_id,
                filename=chunk.document_filename,
                fragment=chunk.chunk_index,
                score=chunk.score,
                download_url=f"{base}/documents/{chunk.document_id}/download",
            )
            for position, chunk in enumerate(chunks, start=1)
        ]

    def _render_prompt(self, question: str, context: str) -> str:
        if not context:
            return (
                "No relevant context was found in the knowledge base.\n\n"
                f"Question: {question}"
            )
        return f"Context:\n{context}\n\nQuestion: {question}"

    def _messages(self, prompt: str) -> list[ChatMessage]:
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
