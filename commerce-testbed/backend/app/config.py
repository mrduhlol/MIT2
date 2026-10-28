from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings.

    All values can be overridden via environment variables.  The defaults are
    development-only values and MUST be changed for any real deployment.
    """

    SECRET_KEY: str = "dev-secret-change-me-not-for-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    AGENT_API_KEY: str = "agent-dev-key-change-me"
    DATABASE_URL: str = "sqlite:///./data/app.db"
    CORS_ORIGINS: str = "http://localhost:5173"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
