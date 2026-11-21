from __future__ import annotations

from pathlib import Path
from typing import Literal, Self

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_AUTH_TOKEN_LENGTH = 16
LOCAL_HOSTS = ("localhost", "127.0.0.1")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="UI_", frozen=True)

    env: Literal["dev", "prod"]
    host: str = "127.0.0.1"
    port: int = 8090
    static_dir: Path = Path("frontend/dist")
    auth_token: str = Field(default="", validation_alias=AliasChoices("AUTH_TOKEN", "auth_token"))
    domain: str = ""

    @model_validator(mode="after")
    def require_auth_token_and_prod_domain(self) -> Self:
        if not self.auth_token:
            raise ValueError("AUTH_TOKEN is required")
        if len(self.auth_token) < MIN_AUTH_TOKEN_LENGTH:
            raise ValueError(f"AUTH_TOKEN must have at least {MIN_AUTH_TOKEN_LENGTH} characters")
        if self.env != "prod":
            return self
        if not self.domain:
            raise ValueError("UI_DOMAIN is required in prod")
        return self

    @property
    def allowed_hosts(self) -> tuple[str, ...]:
        return (*LOCAL_HOSTS, self.domain) if self.domain else LOCAL_HOSTS

    @property
    def cookie_secure(self) -> bool:
        return self.env == "prod"
