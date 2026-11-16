from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, TypeGuard

from pymongo.errors import PyMongoError

from scraper.config_loader import ConfigError

DISCORD_COLLECTION = "discord_settings"
DISCORD_ID = "discord"
SETTINGS_KEYS = (
    "token",
    "default_channel_id",
    "mention_user_id",
    "message_template",
    "max_chars",
)
ID_KEYS = ("default_channel_id", "mention_user_id")
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9._-]+")
SNOWFLAKE_PATTERN = re.compile(r"[0-9]{17,20}")
DEFAULT_MAX_CHARS = 1900
MAX_CHARS_LIMIT = 2000
DEFAULT_MESSAGE_TEMPLATE = (
    "## {title}\n"
    "{company} | {location}\n"
    "\n"
    "**Details**\n"
    "Link: [link]({url})\n"
    "Source: {site}\n"
    "Diposting: {posted_date}\n"
)
TOKEN_HINT_MASK = "••••"
TOKEN_HINT_LENGTH = 4


class DiscordSettingsInvalidError(ConfigError):
    pass


class DiscordSettingsUnavailableError(ConfigError):
    pass


@dataclass(frozen=True)
class StoredDiscordSettings:
    token: str | None = field(repr=False)
    default_channel_id: str | None
    mention_user_id: str | None
    message_template: str
    max_chars: int
    updated_at: str | None


@contextmanager
def _mongo_errors() -> Iterator[None]:
    try:
        yield
    except PyMongoError as exc:
        raise DiscordSettingsUnavailableError(
            f"The Discord settings store cannot be reached ({type(exc).__name__})"
        ) from exc


def is_snowflake(value: Any) -> bool:
    return isinstance(value, str) and SNOWFLAKE_PATTERN.fullmatch(value) is not None


def _is_valid_max_chars(value: Any) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= MAX_CHARS_LIMIT


def _validate_token(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DiscordSettingsInvalidError("token must be a non-empty string")
    token = value.strip()
    if TOKEN_PATTERN.fullmatch(token) is None:
        raise DiscordSettingsInvalidError(
            "token must not contain spaces, line breaks, or other symbols"
        )
    return token


def _validate_id(key: str, value: Any) -> str | None:
    if value is None or value == "":
        return None
    if not is_snowflake(value):
        raise DiscordSettingsInvalidError(
            f"{key} must be a 17 to 20 digit string, or null to clear"
        )
    return value


def _validate_template(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DiscordSettingsInvalidError("message_template must be a non-empty string")
    return value


def _validate_max_chars(value: Any) -> int:
    if not _is_valid_max_chars(value):
        raise DiscordSettingsInvalidError(
            f"max_chars must be a whole number from 1 to {MAX_CHARS_LIMIT}"
        )
    return value


def _validate_patch(patch: Any) -> dict[str, Any]:
    if not isinstance(patch, dict):
        raise DiscordSettingsInvalidError("settings must be a mapping")
    unknown = sorted(set(patch) - set(SETTINGS_KEYS))
    if unknown:
        raise DiscordSettingsInvalidError(f"not a Discord setting: {', '.join(unknown)}")
    validated: dict[str, Any] = {}
    for key, value in patch.items():
        if key == "token":
            validated[key] = _validate_token(value)
        elif key in ID_KEYS:
            validated[key] = _validate_id(key, value)
        elif key == "message_template":
            validated[key] = _validate_template(value)
        else:
            validated[key] = _validate_max_chars(value)
    return validated


def mask_token(token: str) -> str:
    return (
        TOKEN_HINT_MASK + token[-TOKEN_HINT_LENGTH:]
        if len(token) > TOKEN_HINT_LENGTH
        else TOKEN_HINT_MASK
    )


def to_payload(settings: StoredDiscordSettings) -> dict[str, Any]:
    return {
        "configured": settings.token is not None,
        "token_hint": mask_token(settings.token) if settings.token else None,
        "default_channel_id": settings.default_channel_id,
        "mention_user_id": settings.mention_user_id,
        "message_template": settings.message_template,
        "max_chars": settings.max_chars,
        "updated_at": settings.updated_at,
    }


class DiscordSettingsStore:
    def __init__(self, database: Any) -> None:
        self._collection = database[DISCORD_COLLECTION]

    def read(self) -> StoredDiscordSettings:
        with _mongo_errors():
            document = self._collection.find_one({"_id": DISCORD_ID}) or {}
        return StoredDiscordSettings(
            token=document.get("token"),
            default_channel_id=document.get("default_channel_id"),
            mention_user_id=document.get("mention_user_id"),
            message_template=document.get("message_template") or DEFAULT_MESSAGE_TEMPLATE,
            max_chars=document.get("max_chars") or DEFAULT_MAX_CHARS,
            updated_at=document.get("updated_at"),
        )

    def save(self, patch: dict[str, Any]) -> StoredDiscordSettings:
        validated = _validate_patch(patch)
        if validated:
            changed = {key: value for key, value in validated.items() if value is not None}
            cleared = {key: "" for key, value in validated.items() if value is None}
            update: dict[str, Any] = {
                "$set": {**changed, "updated_at": datetime.now(UTC).isoformat()}
            }
            if cleared:
                update["$unset"] = cleared
            with _mongo_errors():
                self._collection.update_one({"_id": DISCORD_ID}, update, upsert=True)
        return self.read()
