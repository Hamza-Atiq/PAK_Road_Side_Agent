"""Application configuration loaded from environment variables.

All settings live here. Never read os.environ elsewhere in the codebase —
import `settings` from this module so behavior stays predictable and testable.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime settings. Values come from .env or process env."""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---------- App ----------
    APP_NAME: str = "roadside-agent"
    APP_ENV: Literal["development", "staging", "production"] = "development"
    APP_BASE_URL: str = "http://localhost:8000"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # ---------- Database ----------
    DATABASE_URL: str
    DATABASE_SYNC_URL: str
    POSTGRES_USER: str = "roadside"
    POSTGRES_PASSWORD: str = "roadside"
    POSTGRES_DB: str = "roadside"

    # ---------- Redis / Celery ----------
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    # ---------- JWT ----------
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ---------- Anthropic ----------
    ANTHROPIC_API_KEY: str = ""
    CLAUDE_MODEL: str = "claude-sonnet-4-6"

    # ---------- OpenRouteService ----------
    ORS_API_KEY: str = ""
    ORS_BASE_URL: str = "https://api.openrouteservice.org"

    # ---------- Twilio ----------
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""
    TWILIO_WHATSAPP_NUMBER: str = ""
    TWILIO_VERIFY_SERVICE_SID: str = ""
    TWILIO_CALLBACK_BASE_URL: str = ""

    # ---------- File uploads ----------
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_MB: int = 10
    ALLOWED_IMAGE_MIME: str = "image/jpeg,image/png,image/webp"
    ALLOWED_AUDIO_MIME: str = "audio/mpeg,audio/mp4,audio/wav,audio/webm,audio/ogg"

    # ---------- CORS ----------
    CORS_ORIGINS: str = "http://localhost:3001,http://localhost:3002,http://localhost:3003"

    # ---------- Rate limits ----------
    RATE_LIMIT_AUTH: str = "10/minute"
    RATE_LIMIT_INCIDENT: str = "5/minute"

    # ---------- Guardrail policy ----------
    ABUSE_SUSPEND_THRESHOLD: int = 5
    ABUSE_WINDOW_HOURS: int = 24

    # ---------- Dispatch policy ----------
    DISPATCH_INITIAL_RADIUS_KM: float = 50.0
    DISPATCH_MAX_RADIUS_KM: float = 100.0
    PROVIDER_OFFLINE_THRESHOLD_SECONDS: int = 90
    ASSIGNED_TIMEOUT_MINUTES: int = 60
    EN_ROUTE_TIMEOUT_MINUTES: int = 180

    # ---------- Backups ----------
    BACKUP_S3_BUCKET: str = ""
    BACKUP_S3_ENDPOINT: str = ""
    BACKUP_S3_ACCESS_KEY: str = ""
    BACKUP_S3_SECRET_KEY: str = ""
    BACKUP_RETENTION_DAYS: int = 30

    # ---------- Monitoring ----------
    PROMETHEUS_ENABLED: bool = True
    GRAFANA_ADMIN_USER: str = "admin"
    GRAFANA_ADMIN_PASSWORD: str = "admin"

    # ---------- Derived helpers ----------
    @property
    def allowed_image_mimes(self) -> list[str]:
        return [m.strip() for m in self.ALLOWED_IMAGE_MIME.split(",") if m.strip()]

    @property
    def allowed_audio_mimes(self) -> list[str]:
        return [m.strip() for m in self.ALLOWED_AUDIO_MIME.split(",") if m.strip()]

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_MB * 1024 * 1024

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @field_validator("JWT_SECRET_KEY")
    @classmethod
    def _jwt_secret_must_be_strong(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters")
        return v


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor. Use this everywhere."""
    return Settings()


settings = get_settings()
