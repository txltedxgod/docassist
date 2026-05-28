"""Application settings loaded from the environment via pydantic-settings."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed runtime configuration.

    Values come from environment variables and an optional ``.env`` file.
    Nothing here is hard-coded that should be a secret; secrets must be supplied
    through the environment.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application ---
    app_name: str = "DocAssist"
    environment: str = "local"
    debug: bool = False
    log_level: str = "INFO"
    log_json: bool = True
    public_base_url: str = "http://localhost:8000"

    # --- HTTP server ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # --- Database ---
    database_url: str = (
        "postgresql+asyncpg://docassist:docassist@localhost:5432/docassist"
    )
    database_url_sync: str = (
        "postgresql+psycopg://docassist:docassist@localhost:5432/docassist"
    )
    db_echo: bool = False

    # --- Object storage ---
    storage_dir: Path = Path("./var/storage")
    max_upload_mb: int = 25
    upload_allowed_extensions: str = "pdf,docx,txt,md"

    # --- LLM / Embeddings (OpenAI-compatible) ---
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    request_timeout: float = 60.0
    llm_max_retries: int = 4
    llm_backoff_base: float = 0.5
    llm_backoff_max: float = 8.0

    # --- RAG ---
    chunk_size_tokens: int = 800
    chunk_overlap_tokens: int = 100
    retrieval_top_k: int = 5
    max_context_tokens: int = 3000

    # --- Background ingestion ---
    ingestion_workers: int = 2
    ingestion_queue_maxsize: int = 100

    # --- Telegram bot ---
    telegram_bot_token: str = ""
    api_base_url: str = "http://localhost:8000"
    telegram_request_timeout: float = 120.0

    max_upload_bytes: int = Field(default=0, exclude=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def allowed_extensions(self) -> frozenset[str]:
        """Normalised set of accepted file extensions (without dots)."""
        return frozenset(
            ext.strip().lower().lstrip(".")
            for ext in self.upload_allowed_extensions.split(",")
            if ext.strip()
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def upload_size_limit(self) -> int:
        """Maximum accepted upload size in bytes."""
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """Return a process-wide cached :class:`Settings` instance."""
    return Settings()
