"""Configuration management for AI Middleware."""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Allow extra env vars like slack_webhook_url
    )

    # Application
    app_name: str = "ai-middleware"
    app_env: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Rate Limiting
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60

    # Provider API Keys
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    google_api_key: Optional[str] = None
    azure_openai_api_key: Optional[str] = None
    azure_openai_endpoint: Optional[str] = None
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_region: str = "us-east-1"
    mistral_api_key: Optional[str] = None
    cohere_api_key: Optional[str] = None

    # OpenAI Model Defaults (configurable via env vars)
    openai_chat_model: str = "gpt-5.2"
    openai_code_model: str = "gpt-5.2"
    openai_image_model: str = "gpt-image-1.5"
    openai_stt_model: str = "gpt-4o-transcribe"
    openai_tts_model: str = "gpt-4o-mini-tts"
    openai_tts_voice: str = "alloy"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()

