from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.domain.errors import BusinessError

VALIDATION_CODE_BY_TYPE = {
    "duplicate_product_id": "DUPLICATE_PRODUCT_ID",
    "extra_forbidden": "UNEXPECTED_FIELD",
    "finite_number": "INVALID_COORDINATES",
    "invalid_coordinates": "INVALID_COORDINATES",
    "products_required": "PRODUCTS_REQUIRED",
    "timezone_required": "TIMEZONE_REQUIRED",
}


async def business_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, BusinessError):
        raise exc
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": [detail.as_dict() for detail in exc.details],
            }
        },
    )


async def validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc
    errors = exc.errors()
    error_code = _validation_error_code(errors)
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": error_code,
                "message": "The request is invalid.",
                "details": [_validation_detail(error) for error in errors],
            }
        },
    )


async def http_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):
        raise exc
    code = "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR"
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": code,
                "message": str(exc.detail),
                "details": [],
            }
        },
        headers=exc.headers,
    )


def _validation_error_code(errors: Sequence[Any]) -> str:
    codes = {
        VALIDATION_CODE_BY_TYPE.get(str(error["type"]), "VALIDATION_ERROR") for error in errors
    }
    return codes.pop() if len(codes) == 1 else "VALIDATION_ERROR"


def _validation_detail(error: Any) -> dict[str, Any]:
    location = [str(part) for part in error.get("loc", ()) if part not in {"body", "query", "path"}]
    return {
        "field": ".".join(location),
        "reason": str(error.get("type", "validation_error")).upper(),
    }
