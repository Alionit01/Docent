from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://postgres:root@localhost:5432/docent"
    llm_provider: str = "groq"
    llm_api_key: str = ""
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_model: str = "llama-3.3-70b-versatile"
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dim: int = 384
    chroma_persist_dir: str = "./data/chroma"
    upload_dir: str = "./data/uploads"
    max_pdf_mb: int = 50
    max_pages: int = 100
    truncate_pages: int = 50

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
