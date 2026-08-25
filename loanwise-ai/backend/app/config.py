"""
Environment-driven configuration. Secrets are never hardcoded or committed
(Section 8.3). In production these come from the platform's secrets
manager / environment; locally they come from a .env file that is
git-ignored from commit one.
"""
from __future__ import annotations

import secrets

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # DATABASE_URL defaults to a local SQLite file so the reference
    # implementation runs without external services. Set to a Postgres DSN
    # (postgresql+psycopg2://...) for production — see README "Why Postgres".
    database_url: str = "sqlite:///./loanwise.db"

    jwt_secret_key: str = secrets.token_urlsafe(32)  # dev-only fallback; override via env in prod
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    rate_limit_predict: str = "20/minute"
    rate_limit_whatif: str = "20/minute"
    rate_limit_login: str = "10/minute"

    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    environment: str = "development"


settings = Settings()
