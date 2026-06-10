"""FastAPI dependency providers wiring repositories and services together."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.repositories.chunks import ChunkRepository
from app.repositories.conversations import ConversationRepository
from app.repositories.documents import DocumentRepository
from app.services.embeddings import EmbeddingClient
from app.services.llm import LLMClient
from app.services.queue import IngestionQueue
from app.services.rag import RAGService
from app.services.retrieval import RetrievalService
from app.services.storage import FileStorage

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_storage(request: Request) -> FileStorage:
    """Return the process-wide file storage held on app state."""
    return request.app.state.storage


def get_ingestion_queue(request: Request) -> IngestionQueue:
    """Return the running ingestion queue held on app state."""
    return request.app.state.ingestion_queue


def get_embedding_client(request: Request) -> EmbeddingClient:
    """Return the shared embedding client."""
    return request.app.state.embedding_client


def get_llm_client(request: Request) -> LLMClient:
    """Return the shared LLM client."""
    return request.app.state.llm_client


def get_document_repository(session: SessionDep) -> DocumentRepository:
    return DocumentRepository(session)


def get_conversation_repository(session: SessionDep) -> ConversationRepository:
    return ConversationRepository(session)


def get_rag_service(
    session: SessionDep,
    embedding_client: Annotated[EmbeddingClient, Depends(get_embedding_client)],
    llm_client: Annotated[LLMClient, Depends(get_llm_client)],
) -> RAGService:
    """Assemble a request-scoped RAG service."""
    retrieval = RetrievalService(ChunkRepository(session), embedding_client)
    return RAGService(
        retrieval=retrieval,
        llm=llm_client,
        conversations=ConversationRepository(session),
    )


StorageDep = Annotated[FileStorage, Depends(get_storage)]
QueueDep = Annotated[IngestionQueue, Depends(get_ingestion_queue)]
DocumentRepoDep = Annotated[DocumentRepository, Depends(get_document_repository)]
ConversationRepoDep = Annotated[
    ConversationRepository, Depends(get_conversation_repository)
]
RAGServiceDep = Annotated[RAGService, Depends(get_rag_service)]
