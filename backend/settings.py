from __future__ import annotations

from pathlib import Path
from typing import Literal, Self

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_SESSION_SECRET_LENGTH = 32
MIN_AUTH_TOKEN_LENGTH = 16
LOCAL_HOSTS = ("localhost", "127.0.0.1")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="UI_", frozen=True)

    env: Literal["dev", "prod"]
    host: str = "127.0.0.1"
    port: int = 8090
    static_dir: Path = Path("frontend/dist")
    password_hash: str = ""
    auth_token: str = Field(default="", validation_alias=AliasChoices("AUTH_TOKEN", "auth_token"))
    session_secret: str = ""
    domain: str = ""

    @model_validator(mode="after")
    def require_prod_secrets(self) -> Self:
        if self.auth_token and len(self.auth_token) < MIN_AUTH_TOKEN_LENGTH:
            raise ValueError(f"AUTH_TOKEN must have at least {MIN_AUTH_TOKEN_LENGTH} characters")
        if self.env != "prod":
            if not self.auth_token:
                raise ValueError("AUTH_TOKEN is required in dev")
            return self
        if not self.password_hash:
            raise ValueError("UI_PASSWORD_HASH is required in prod")
        if len(self.session_secret) < MIN_SESSION_SECRET_LENGTH:
            raise ValueError(
                f"UI_SESSION_SECRET must have at least {MIN_SESSION_SECRET_LENGTH} characters"
            )
        if not self.domain:
            raise ValueError("UI_DOMAIN is required in prod")
        return self

    @property
    def allowed_hosts(self) -> tuple[str, ...]:
        return (*LOCAL_HOSTS, self.domain) if self.domain else LOCAL_HOSTS

    @property
    def cookie_secure(self) -> bool:
        return self.env == "prod"
