"""Error envelope from contracts/README.md:
{"error": {"code", "message", "details", "request_id"}}.
"""

import logging
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("infraguard")

REQUEST_ID_HEADER = "X-Request-ID"


class ApiError(Exception):
    """Raise from services or routes to return a contract error."""

    def __init__(self, status_code: int, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}


def not_found(code: str, message: str, **details: Any) -> ApiError:
    return ApiError(404, code, message, details)


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or f"req-{uuid.uuid4().hex[:12]}"


def error_response(request: Request, status_code: int, code: str, message: str, details: dict[str, Any]) -> JSONResponse:
    rid = _request_id(request)
    body = {"error": {"code": code, "message": message, "details": jsonable_encoder(details), "request_id": rid}}
    return JSONResponse(status_code=status_code, content=body, headers={REQUEST_ID_HEADER: rid})


_HTTP_CODES = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}


def install_error_handlers(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request.state.request_id = incoming[:64] if incoming else f"req-{uuid.uuid4().hex[:12]}"
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request.state.request_id
        return response

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError):
        return error_response(request, exc.status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        # Drop "input" and "ctx" so request bodies and exception objects are never echoed back.
        errors = [{"loc": list(e.get("loc", ())), "msg": e.get("msg", ""), "type": e.get("type", "")} for e in exc.errors()]
        return error_response(request, 422, "VALIDATION_ERROR", "Request validation failed.", {"errors": errors})

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException):
        code = _HTTP_CODES.get(exc.status_code, "HTTP_ERROR")
        message = exc.detail if isinstance(exc.detail, str) else "HTTP error."
        return error_response(request, exc.status_code, code, message, {})

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception):
        logger.exception("Unhandled error", extra={"request_id": _request_id(request)})
        return error_response(request, 500, "INTERNAL_ERROR", "Internal server error.", {})
