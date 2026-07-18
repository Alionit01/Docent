from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.errors import AppError, app_error_handler
from app.core.middleware import RequestLoggingMiddleware, UploadRateLimitMiddleware
from app.api import documents, ask, teaching


def create_app() -> FastAPI:
    app = FastAPI(title="Docent", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://localhost:8000",
            "http://localhost:5500",
            "null",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(UploadRateLimitMiddleware, max_concurrent=2)
    app.add_middleware(RequestLoggingMiddleware)

    app.add_exception_handler(AppError, app_error_handler)
    app.include_router(documents.router)
    app.include_router(ask.router)
    app.include_router(teaching.router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
