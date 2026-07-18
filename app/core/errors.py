from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, Any


class ErrorResponse(BaseModel):
    detail: str
    code: str
    meta: Optional[dict] = None


class AppError(Exception):
    def __init__(self, detail: str, code: str, status: int = 400, meta: Optional[dict] = None):
        self.detail = detail
        self.code = code
        self.status = status
        self.meta = meta


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status,
        content=ErrorResponse(detail=exc.detail, code=exc.code, meta=exc.meta).model_dump(),
    )
