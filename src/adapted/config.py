from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---
    app_name: str = "AdaptED"
    app_env: str = "development"
    debug: bool = True
    secret_key: str = "change-me-to-a-long-random-string"
    cors_origins: str = "http://localhost:8501,http://localhost:8000"
    storage_dir: str = "./storage"

    # --- Database ---
    database_url: str = ""

    # --- LLM ---
    llm_provider: str = "mock"  # mock | openrouter
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_api_key: str = ""
    llm_model: str = "openrouter/free"
    embed_model: str = "nvidia/nemotron-3-embed-1b:free"

    # --- LLM cost estimation (USD per 1000 tokens; 0 for free models) ---
    # Used only to estimate spend for the observability dashboard. Set these to
    # your model's real rates for accurate figures.
    llm_price_input_per_1k: float = 0.0
    llm_price_output_per_1k: float = 0.0

    # --- Embeddings ---
    # Real embeddings come from the OpenRouter embed provider (free models only).
    # "mock" keeps vectors deterministic for offline dev/test runs.
    embed_provider: str = "mock"  # mock | openrouter
    embedding_dim: int = 2048

    # --- SearXNG ---
    searxng_url: str = ""
    searxng_insecure: bool = False

    # --- JWT ---
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 720

    # --- Behaviour ---
    default_daily_study_minutes: int = 90
    max_upload_bytes: int = 50 * 1024 * 1024
    rag_top_k: int = 6
    agent_max_retries: int = 2
    agent_retry_backoff_seconds: float = 0.5
    # per-request bound for chat/embed calls; a hung free model becomes a
    # timed-out error -> savepoint rollback -> bounded retry -> loud failure
    llm_timeout_seconds: float = 120

    @property
    def redacted_database_url(self) -> str:
        """database_url with the password masked (safe for logs and /health)."""
        url = self.database_url
        if not url or "@" not in url:
            return url or "<unset>"
        scheme, _, rest = url.partition("://")
        userinfo, _, host = rest.rpartition("@")
        if userinfo and ":" in userinfo:
            user, _, _ = userinfo.partition(":")
            userinfo = f"{user}:***"
        return f"{scheme}://{userinfo}@{host}" if userinfo else url

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def storage_path(self) -> Path:
        p = Path(self.storage_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
