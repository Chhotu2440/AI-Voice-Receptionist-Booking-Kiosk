"""Domain errors and the global error envelope (see docs/09-api-specification.md)."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_ctx

log = logging.getLogger(__name__)


class DomainError(Exception):
    """Base class for expected, client-facing errors. Messages must be safe to show to customers."""

    status_code: int = 400
    code: str = "BAD_REQUEST"
    default_message: str = "The request could not be processed."

    def __init__(self, message: str | None = None, *, details: dict[str, Any] | None = None) -> None:
        self.message = message or self.default_message
        self.details = details or {}
        super().__init__(self.message)


class NotFoundError(DomainError):
    status_code, code, default_message = 404, "NOT_FOUND", "Not found."


class ConflictError(DomainError):
    status_code, code, default_message = 409, "CONFLICT", "The request conflicts with the current state."


class ValidationFailed(DomainError):
    status_code, code, default_message = 422, "VALIDATION_ERROR", "Some details are not valid."


class UnauthenticatedError(DomainError):
    status_code, code, default_message = 401, "UNAUTHENTICATED", "Authentication is required."


class ForbiddenError(DomainError):
    status_code, code, default_message = 403, "FORBIDDEN", "You do not have permission to do that."


class RateLimitedError(DomainError):
    status_code, code, default_message = 429, "RATE_LIMITED", "Too many requests. Please try again shortly."


class GuestCountInvalidError(DomainError):
    status_code, code, default_message = 422, "GUEST_COUNT_INVALID", "That group size is not allowed."


class OutsideBookingWindowError(DomainError):
    status_code, code, default_message = 422, "OUTSIDE_BOOKING_WINDOW", "That date can't be booked."


class PricingNotConfiguredError(DomainError):
    status_code, code, default_message = (
        422,
        "PRICING_NOT_CONFIGURED",
        "No price is configured for that date.",
    )


def _envelope(status: int, code: str, message: str, details: dict[str, Any] | None = None) -> JSONResponse:
    body = {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": request_id_ctx.get(),
        }
    }
    return JSONResponse(status_code=status, content=body)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain(_: Request, exc: DomainError) -> JSONResponse:
        return _envelope(exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"loc": list(e.get("loc", ())), "msg": e.get("msg", ""), "type": e.get("type", "")}
            for e in exc.errors()
        ]
        return _envelope(422, "VALIDATION_ERROR", "Some details are not valid.", {"errors": errors})

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {401: "UNAUTHENTICATED", 403: "FORBIDDEN", 404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(
            exc.status_code, "HTTP_ERROR"
        )
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return _envelope(exc.status_code, code, message)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error", exc_info=exc)
        return _envelope(500, "INTERNAL", "Something went wrong on our side. Please try again.")
