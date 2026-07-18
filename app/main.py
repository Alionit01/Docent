from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.errors import AppError, app_error_handler
from app.api import documents


def create_app() -> FastAPI:
    app = FastAPI(title="Docent", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_exception_handler(AppError, app_error_handler)
    app.include_router(documents.router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


app = create_app()
