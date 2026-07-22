"""Shared retry helpers for transient rate limiting."""

from __future__ import annotations

import datetime as dt
import email.utils
import logging
import time
from collections.abc import Callable
from typing import TypeVar


ResultT = TypeVar("ResultT")


def _status_code(exc: Exception) -> int | None:
    status_code = getattr(exc, "status_code", None)
    if status_code is not None:
        return status_code
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", None)


def _retry_after_seconds(exc: Exception) -> float | None:
    headers = getattr(exc, "headers", None)
    if headers is None:
        response = getattr(exc, "response", None)
        headers = getattr(response, "headers", None)
    if not headers:
        return None
    retry_after = headers.get("Retry-After")
    if not retry_after:
        return None
    try:
        return max(float(retry_after), 0.0)
    except (TypeError, ValueError):
        pass
    try:
        retry_at = email.utils.parsedate_to_datetime(retry_after)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=dt.timezone.utc)
    delay = (retry_at - dt.datetime.now(dt.timezone.utc)).total_seconds()
    return max(delay, 0.0)


def run_with_429_backoff(
    operation: Callable[[], ResultT],
    *,
    logger: logging.Logger,
    description: str,
    max_attempts: int = 6,
    initial_delay: float = 2.0,
    max_delay: float = 120.0,
) -> ResultT:
    """Retry an operation when it fails with an HTTP 429."""
    delay = initial_delay
    for attempt in range(1, max_attempts + 1):
        try:
            return operation()
        except Exception as exc:
            if _status_code(exc) != 429 or attempt == max_attempts:
                raise
            retry_after = _retry_after_seconds(exc)
            wait_seconds = retry_after if retry_after is not None else delay
            logger.warning(
                "Received 429 while %s; retrying in %.1fs (attempt %d/%d).",
                description,
                wait_seconds,
                attempt,
                max_attempts,
            )
            time.sleep(wait_seconds)
            delay = min(delay * 2, max_delay)

    raise RuntimeError("429 retry loop exited unexpectedly")