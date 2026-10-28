from functools import lru_cache
from typing import Literal, Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    app_name: str = "niche-social-network"
    app_env: Literal["development", "testing", "production"] = "development"
    app_debug: bool = False
    app_demo_mode: bool = False
    api_v1_prefix: str = "/api/v1"
    auth_secret: SecretStr = SecretStr("local-development-only-change-before-deployment")
    access_token_seconds: int = 3600

    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_database: str = "niche_social"
    redis_url: str = "redis://localhost:6379/0"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr = SecretStr("")

    @model_validator(mode="after")
    def prevent_demo_mode_in_production(self) -> Self:
        if self.app_env == "production" and (
            self.auth_secret.get_secret_value() == "local-development-only-change-before-deployment"
            or len(self.auth_secret.get_secret_value()) < 32
        ):
            raise ValueError("Production requires AUTH_SECRET with at least 32 characters")
        if self.app_env == "production" and self.app_demo_mode:
            raise ValueError("APP_DEMO_MODE cannot be enabled in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
