from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    data_dir: str = Field(default="./data", description="Directory to store analysis results and repos")
    allow_origins: str = Field(default="*", description="CORS allowed origins")
    database_url: str = Field(
        default="postgresql://assistant:password@localhost:5432/repo_assistant",
        description="Postgres database URL",
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis broker URL for Celery",
    )

    # Ollama configuration
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Base URL for the local Ollama server",
    )
    ollama_model: str = Field(
        default="llama3",
        description="Ollama chat model to use for RAG (e.g. llama3, mistral, codellama)",
    )
    ollama_embed_model: str = Field(
        default="nomic-embed-text",
        description="Ollama embedding model to use for pgvector indexing",
    )

    class Config:
        env_prefix = "RUA_"


settings = Settings()
