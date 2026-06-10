"""FastAPI application factory and lifespan wiring."""
from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.errors import register_exception_handlers
from app.api.routes import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import dispose_engine, get_session_factory
from app.services.embeddings import EmbeddingClient
from app.services.llm import LLMClient
from app.services.queue import IngestionQueue
from app.services.storage import FileStorage

_STATIC_DIR = Path(__file__).parent / "static"
_logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialise shared singletons and the background ingestion queue."""
    configure_logging()
    settings = get_settings()

    storage = FileStorage(settings.storage_dir)
    embedding_client = EmbeddingClient(settings)
    llm_client = LLMClient(settings)
    queue = IngestionQueue(
        get_session_factory(),
        storage=storage,
        embedding_client=embedding_client,
        settings=settings,
    )
    await queue.start()

    app.state.storage = storage
    app.state.embedding_client = embedding_client
    app.state.llm_client = llm_client
    app.state.ingestion_queue = queue
    _logger.info("app_started", app=settings.app_name, version=__version__)

    try:
        yield
    finally:
        await queue.stop()
        await dispose_engine()
        _logger.info("app_stopped")


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()
    configure_logging()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        summary="RAG assistant over your documents.",
        lifespan=lifespan,
    )
    register_exception_handlers(app)
    app.include_router(api_router)

    if _STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

        @app.get("/", include_in_schema=False)
        async def dashboard() -> FileResponse:
            return FileResponse(_STATIC_DIR / "index.html")

    return app


app = create_app()
