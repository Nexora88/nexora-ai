import os
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Nexora AI"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    DATABASE_URL: Optional[str] = None

    SECRET_KEY: Optional[str] = None
    JWT_SECRET: Optional[str] = None
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    # LLM
    GROQ_API_KEY: Optional[str] = None
    GOOGLE_API_KEY: Optional[str] = None
    OPENROUTER_API_KEY: Optional[str] = None
    MISTRAL_API_KEY: Optional[str] = None
    COHERE_API_KEY: Optional[str] = None
    CEREBRAS_API_KEY: Optional[str] = None
    TOGETHER_API_KEY: Optional[str] = None
    DEEPSEEK_API_KEY: Optional[str] = None
    FIREWORKS_API_KEY: Optional[str] = None
    XAI_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    OPENWEATHER_API_KEY: Optional[str] = None
    TOMTOM_API_KEY: Optional[str] = None
    ORS_API_KEY: Optional[str] = None
    NASA_API_KEY: Optional[str] = None
    FINNHUB_API_KEY: Optional[str] = None
    TWELVEDATA_API_KEY: Optional[str] = None
    ALPHA_VANTAGE_API_KEY: Optional[str] = None
    NEWSAPI_KEY: Optional[str] = None
    GITHUB_APP_ID: Optional[str] = None
    GITHUB_PRIVATE_KEY: Optional[str] = None

    # Search / media
    TAVILY_API_KEY: Optional[str] = None
    REPLICATE_API_TOKEN: Optional[str] = None
    WEATHER_API_KEY: Optional[str] = None

    # Stripe
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None
    STRIPE_PRO_PRICE_ID: Optional[str] = None
    STRIPE_ELITE_PRICE_ID: Optional[str] = None

    # GitHub Ship
    GITHUB_CLIENT_ID: Optional[str] = None
    GITHUB_CLIENT_SECRET: Optional[str] = None
    GITHUB_REDIRECT_URI: str = "http://localhost:8000/api/v1/ship/callback"
    FRONTEND_URL: str = "http://localhost:3000"
    SUPABASE_URL: Optional[str] = None
    SUPABASE_ANON_KEY: Optional[str] = None
    # Railway injects PORT at runtime; FRONTEND_URL is also used by CORS and OAuth callbacks.
    SHIP_TOKEN_COST: int = 10

    FREE_MESSAGES_LIMIT: int = 5
    PRO_MESSAGES_LIMIT: int = 400
    ELITE_MESSAGES_LIMIT: int = 2000

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )

    def validate_production(self) -> None:
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
            raise RuntimeError("Production eksik: " + ", ".join(missing))


@lru_cache()
def get_settings() -> Settings:
    s = Settings()
    s.validate_production()
    return s
