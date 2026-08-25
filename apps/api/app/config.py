from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Sofia"
    environment: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    database_url: str = "postgresql+asyncpg://sofia:sofia@localhost:5432/sofia"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: str = "http://localhost:5173"
    ai_provider: str = "groq"
    ai_fallback_provider: str = "openrouter"
    ai_timeout_seconds: float = 30.0
    app_url: str = "http://localhost:5173"
    groq_model: str = "llama-3.3-70b-versatile"
    openrouter_model: str = "meta-llama/llama-3.3-70b-instruct:free"
    groq_api_key: str = ""
    openrouter_api_key: str = ""
    evolution_api_url: str = ""
    evolution_api_key: str = ""
    evolution_instance: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
