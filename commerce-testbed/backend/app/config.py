from functools import lru_cache
from contextvars import ContextVar, Token

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


_request_settings: ContextVar[Settings | None] = ContextVar(
    "commerce_testbed_settings", default=None
)


def set_request_settings(settings: Settings) -> Token[Settings | None]:
    """Use Worker-bound settings for the lifetime of one request."""
    return _request_settings.set(settings)


def reset_request_settings(token: Token[Settings | None]) -> None:
    _request_settings.reset(token)


@lru_cache
def _default_settings() -> Settings:
    return Settings()


def get_settings() -> Settings:
    """Return per-request Worker bindings, or cached local environment settings."""
    return _request_settings.get() or _default_settings()
