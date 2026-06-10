"""Health endpoint."""
from __future__ import annotations

from fastapi import APIRouter

from app import __version__
from app.core.config import get_settings
from app.schemas.common import HealthResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Report service liveness."""
    settings = get_settings()
    return HealthResponse(status="ok", app=settings.app_name, version=__version__)
