"""Application settings loaded from environment (.env)."""

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Database (use postgresql+asyncpg:// for async)
    DATABASE_URL: str

    # Auth 
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_EXPIRE_MIN: int
    REFRESH_EXPIRE_DAYS: int

    # Redis
    REDIS_URL: str

    # CORS
    CORS_ORIGINS: list[str]

    # Frontend
    FRONTEND_URL: str

    # Development
    DEBUG: bool

    # Email (SMTP) 
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    EMAILS_FROM_EMAIL: str | None = None
    EMAILS_FROM_NAME: str | None = None

    # Logging
    LOG_LEVEL: str = "INFO"

    # Rate limiting (public endpoints)
    RATE_LIMIT_ENABLED: bool

    # Load from .env; keys are case-sensitive (e.g. DATABASE_URL not database_url).
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


# Singleton used across the app (database, auth, Redis, etc.).
settings = Settings()
