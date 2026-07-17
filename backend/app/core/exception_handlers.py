"""
Global exception handlers.

Registered on the FastAPI app in `app/main.py`. These translate our
framework-agnostic domain exceptions (`app/core/exceptions.py`) into
consistent JSON error responses, and make sure unexpected errors are
logged with full context rather than leaking raw stack traces to
clients in production.
"""

import structlog
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.exceptions import (
    AuthError,
    CivicAIError,
    ConflictError,
    FileTooLargeError,
    InvalidCredentialsError,
    InvalidTokenError,
    NotFoundError,
    PermissionDeniedError,
    UnsupportedFileTypeError,
    ValidationError,
)

logger = structlog.get_logger(__name__)

_STATUS_MAP = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
    ValidationError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    InvalidCredentialsError: status.HTTP_401_UNAUTHORIZED,
    InvalidTokenError: status.HTTP_401_UNAUTHORIZED,
    PermissionDeniedError: status.HTTP_403_FORBIDDEN,
    AuthError: status.HTTP_401_UNAUTHORIZED,
    FileTooLargeError: status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
    UnsupportedFileTypeError: status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
}


def _status_for(exc: CivicAIError) -> int:
    """Walk the exception's MRO to find the most specific mapped status code."""
    for exc_type in type(exc).__mro__:
        if exc_type in _STATUS_MAP:
            return _STATUS_MAP[exc_type]
    return status.HTTP_400_BAD_REQUEST


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(CivicAIError)
    async def civicai_error_handler(request: Request, exc: CivicAIError) -> JSONResponse:
        status_code = _status_for(exc)
        logger.warning(
            "handled_domain_exception",
            path=request.url.path,
            method=request.method,
            exception_type=type(exc).__name__,
            detail=exc.message,
        )
        return JSONResponse(
            status_code=status_code,
            content={"error": type(exc).__name__, "detail": exc.message},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        settings = get_settings()
        logger.error(
            "unhandled_exception",
            path=request.url.path,
            method=request.method,
            exception_type=type(exc).__name__,
            exc_info=True,
        )
        detail = str(exc) if settings.DEBUG else "An internal server error occurred."
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": "InternalServerError", "detail": detail},
        )