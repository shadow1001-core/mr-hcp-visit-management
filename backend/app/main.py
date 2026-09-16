from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.error_handlers import (
    business_error_handler,
    http_error_handler,
    validation_error_handler,
)
from app.api.router import api_router
from app.core.config import get_settings
from app.domain.errors import BusinessError

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
)
app.add_exception_handler(BusinessError, business_error_handler)
app.add_exception_handler(RequestValidationError, validation_error_handler)
app.add_exception_handler(StarletteHTTPException, http_error_handler)
app.include_router(api_router)
