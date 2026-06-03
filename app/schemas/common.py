"""Shared API schema primitives."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Uniform error envelope returned by every failing endpoint."""

    code: str = Field(description="Stable machine-readable error code.")
    message: str = Field(description="Human-readable error description.")
    detail: object | None = Field(default=None, description="Optional structured detail.")


class HealthResponse(BaseModel):
    """Liveness/readiness payload."""

    status: str
    app: str
    version: str
