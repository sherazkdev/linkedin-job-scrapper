import logging

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class AppError(Exception):
    def __init__(self, message: str, *, code: str = "app_error") -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, code="not_found")


def _error_body(*, code: str, message: str) -> dict:
    return {"success": False, "error": {"code": code, "message": message}}


def register_exception_handlers(app) -> None:
    @app.exception_handler(NotFoundError)
    async def not_found_handler(_request: Request, exc: NotFoundError) -> JSONResponse:
        body = _error_body(code=exc.code, message=exc.message)
        return JSONResponse(status_code=404, content=body)

    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        body = _error_body(code=exc.code, message=exc.message)
        return JSONResponse(status_code=400, content=body)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail
        if isinstance(detail, str):
            message = detail
        elif isinstance(detail, dict):
            message = str(detail.get("message", detail))
        else:
            message = str(detail)
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(code="http_error", message=message),
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(
        _request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        settings = get_settings()
        if settings.is_production:
            message = "Invalid request parameters"
        else:
            message = "; ".join(
                f"{'.'.join(str(p) for p in err.get('loc', ()))}: {err.get('msg', 'invalid')}"
                for err in exc.errors()[:5]
            )
        return JSONResponse(
            status_code=422,
            content=_error_body(code="validation_error", message=message),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        settings = get_settings()
        if settings.is_production:
            message = "Internal server error"
        else:
            message = f"{type(exc).__name__}: internal error"
        return JSONResponse(
            status_code=500,
            content=_error_body(code="internal_error", message=message),
        )