"""Exception handlers translating errors into the uniform JSON envelope."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppError
from app.core.logging import get_logger
from app.schemas.common import ErrorResponse

_logger = get_logger(__name__)


def _envelope(status_code: int, code: str, message: str, detail: object = None) -> JSONResponse:
    payload = ErrorResponse(code=code, message=message, detail=detail)
    return JSONResponse(status_code=status_code, content=payload.model_dump())


def register_exception_handlers(app: FastAPI) -> None:
    """Attach application-wide exception handlers."""

    @app.exception_handler(AppError)
    async def _handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        if exc.status_code >= 500:
            _logger.error("app_error", code=exc.code, message=exc.message)
        return _envelope(exc.status_code, exc.code, exc.message, exc.detail)

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return _envelope(422, "validation_error", "Request validation failed.", exc.errors())

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _envelope(exc.status_code, "http_error", str(exc.detail))

    @app.exception_handler(Exception)
    async def _handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        _logger.exception("unhandled_exception", error=str(exc))
        return _envelope(500, "internal_error", "An unexpected error occurred.")
