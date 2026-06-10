"""API routers aggregated under a single entry point."""
from fastapi import APIRouter

from app.api.routes import chat, conversations, documents, health

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(documents.router)
api_router.include_router(chat.router)
api_router.include_router(conversations.router)

__all__ = ["api_router"]
