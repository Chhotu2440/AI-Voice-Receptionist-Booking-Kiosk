"""Retry a whole unit of work when MySQL reports a deadlock or lock-wait timeout."""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable

from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

RETRYABLE_MYSQL_CODES = {1205, 1213}  # lock wait timeout, deadlock


def _is_retryable(exc: DBAPIError) -> bool:
    orig = getattr(exc, "orig", None)
    args: tuple[object, ...] = tuple(getattr(orig, "args", ()))
    return bool(args) and isinstance(args[0], int) and args[0] in RETRYABLE_MYSQL_CODES


async def run_with_retry[T](
    session: AsyncSession,
    work: Callable[[], Awaitable[T]],
    *,
    attempts: int = 4,
    retry_integrity: bool = False,
) -> T:
    """Run `work` (a complete transaction that commits), retrying from the start on deadlocks.

    `retry_integrity` also retries unique collisions (e.g. randomly generated references)."""
    for attempt in range(1, attempts + 1):
        try:
            return await work()
        except IntegrityError:
            await session.rollback()
            if not retry_integrity or attempt == attempts:
                raise
        except DBAPIError as exc:
            await session.rollback()
            if not _is_retryable(exc) or attempt == attempts:
                raise
            log.warning("db_retry", extra={"attempt": attempt, "error_code": exc.orig.args[0]})  # type: ignore[union-attr]
        await asyncio.sleep(random.uniform(0.01, 0.05) * attempt)  # noqa: S311 (jitter, not crypto)
    raise RuntimeError("unreachable")
