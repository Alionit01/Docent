import time
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        duration = time.time() - start
        logger.info(
            f"{request.method} {request.url.path} -> {response.status_code} ({duration:.3f}s)"
        )
        return response


class UploadRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, max_concurrent: int = 2):
        super().__init__(app)
        self.max_concurrent = max_concurrent
        self._active: dict[str, int] = {}

    async def dispatch(self, request: Request, call_next):
        if request.url.path.endswith("/upload") and request.method == "POST":
            client_ip = request.client.host if request.client else "unknown"
            current = self._active.get(client_ip, 0)
            if current >= self.max_concurrent:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many concurrent uploads. Try again later.", "code": "RATE_LIMITED"},
                )
            self._active[client_ip] = current + 1
            try:
                response = await call_next(request)
            finally:
                self._active[client_ip] -= 1
                if self._active[client_ip] <= 0:
                    del self._active[client_ip]
            return response

        return await call_next(request)
