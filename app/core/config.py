import os
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Nexora AI"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    # Production (Vercel) MUST use a persistent PostgreSQL database.
    # Local development can continue using SQLite.
    DATABASE_URL: Optional[str] = None

    # Never use placeholder secrets in production.
    SECRET_KEY: Optional[str] = None
    JWT_SECRET: Optional[str] = None
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    GROQ_API_KEY: Optional[str] = None
    GOOGLE_API_KEY: Optional[str] = None
    OPENROUTER_API_KEY: Optional[str] = None
    XAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None

    # Stripe
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None
    STRIPE_PRO_PRICE_ID: Optional[str] = None
    STRIPE_ELITE_PRICE_ID: Optional[str] = None

    FREE_MESSAGES_LIMIT: int = 5
    PRO_MESSAGES_LIMIT: int = 400
    ELITE_MESSAGES_LIMIT: int = 2000

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )

    def validate_production(self) -> None:
        """Fail fast instead of silently using an ephemeral DB or unsafe secrets."""
        is_vercel = os.getenv("VERCEL") == "1"
        is_production = self.ENVIRONMENT.lower() == "production" or is_vercel

        if not is_production:
            return

        missing = []
        if not self.DATABASE_URL:
            missing.append("DATABASE_URL")
        if not self.SECRET_KEY:
            missing.append("SECRET_KEY")
        if not self.JWT_SECRET:
            missing.append("JWT_SECRET")

        if missing:
            raise RuntimeError(
                "Production configuration is incomplete. Missing environment variables: "
                + ", ".join(missing)
            )


@lru_cache()
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_production()
    return settings
