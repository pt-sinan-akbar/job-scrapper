from __future__ import annotations

from typing import Annotated, Any, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

MAX_TEXT_CHARS = 2000
MAX_JOBS = 50
SNOWFLAKE_DIGITS = r"[0-9]{17,20}"

Snowflake = Annotated[str, StringConstraints(pattern=rf"^{SNOWFLAKE_DIGITS}$")]
ClearableSnowflake = Annotated[str, StringConstraints(pattern=rf"^({SNOWFLAKE_DIGITS})?$")]
Token = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=200, pattern=r"^[A-Za-z0-9._-]+$"),
]


class DiscordSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: Token | None = None
    default_channel_id: ClearableSnowflake | None = None
    mention_user_id: ClearableSnowflake | None = None
    message_template: str | None = Field(default=None, min_length=1)
    max_chars: int | None = Field(default=None, ge=1, le=MAX_TEXT_CHARS)

    @model_validator(mode="after")
    def _reject_null_required_fields(self) -> Self:
        for name in ("token", "message_template", "max_chars"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be cleared")
        return self

    def to_patch(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_unset=True)


class DiscordMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mention: bool
    text: str = Field(min_length=1, max_length=MAX_TEXT_CHARS)


class DiscordSendRequest(DiscordMessageRequest):
    channel_id: Snowflake
