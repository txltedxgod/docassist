"""Async retry helper with exponential backoff and full jitter.

Kept dependency-free on purpose: retrying transient LLM/embedding failures is
core behaviour, so we don't want it to hinge on an optional third-party library.
"""
from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable, Iterable
from typing import TypeVar

from app.core.logging import get_logger

T = TypeVar("T")
_logger = get_logger(__name__)


async def retry_async(
    func: Callable[[], Awaitable[T]],
    *,
    retry_on: tuple[type[BaseException], ...],
    max_attempts: int,
    base_delay: float,
    max_delay: float,
    operation: str,
) -> T:
    """Call ``func`` repeatedly until it succeeds or attempts are exhausted.

    Args:
        func: Zero-argument coroutine factory to execute.
        retry_on: Exception types that are considered transient.
        max_attempts: Total number of attempts (>= 1).
        base_delay: Base backoff delay in seconds.
        max_delay: Upper bound for any single backoff delay.
        operation: Short label used in structured logs.

    Returns:
        The successful result of ``func``.

    Raises:
        BaseException: The last exception raised once attempts are exhausted, or
            immediately for exceptions not listed in ``retry_on``.
    """
    attempts = max(1, max_attempts)
    last_exc: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await func()
        except retry_on as exc:
            last_exc = exc
            if attempt == attempts:
                break
            delay = min(max_delay, base_delay * 2 ** (attempt - 1))
            delay = random.uniform(0, delay)  # full jitter avoids thundering herd
            _logger.warning(
                "retrying_operation",
                operation=operation,
                attempt=attempt,
                max_attempts=attempts,
                delay=round(delay, 3),
                error=str(exc),
            )
            await asyncio.sleep(delay)

    assert last_exc is not None  # loop only exits via return or a caught error
    raise last_exc


def as_tuple(exc_types: Iterable[type[BaseException]]) -> tuple[type[BaseException], ...]:
    """Materialise an iterable of exception types into a tuple."""
    return tuple(exc_types)
