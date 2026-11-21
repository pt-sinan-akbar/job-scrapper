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


def is_snowflake(candidate_id: Any) -> bool:
    if not isinstance(candidate_id, str):
        return False
    return SNOWFLAKE_PATTERN.fullmatch(candidate_id) is not None


def mask_token(token: str) -> str:
    if len(token) <= TOKEN_HINT_LENGTH:
        return TOKEN_HINT_MASK
    return TOKEN_HINT_MASK + token[-TOKEN_HINT_LENGTH:]


def build_settings_payload(settings: StoredDiscordSettings) -> dict[str, Any]:
    return {
        "configured": settings.token is not None,
        "token_hint": _build_token_hint(settings.token),
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
        with _translate_mongo_errors():
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
        validated_patch = _validate_patch(patch)
        if validated_patch:
            mongo_update = _build_mongo_update(validated_patch)
            with _translate_mongo_errors():
                self._collection.update_one({"_id": DISCORD_ID}, mongo_update, upsert=True)
        return self.read()


@contextmanager
def _translate_mongo_errors() -> Iterator[None]:
    try:
        yield
    except PyMongoError as exc:
        raise DiscordSettingsUnavailableError(
            f"The Discord settings store cannot be reached ({type(exc).__name__})"
        ) from exc


def _build_token_hint(token: str | None) -> str | None:
    if not token:
        return None
    return mask_token(token)


def _is_valid_max_chars(max_chars: Any) -> TypeGuard[int]:
    if not isinstance(max_chars, int):
        return False
    if isinstance(max_chars, bool):
        return False
    return 1 <= max_chars <= MAX_CHARS_LIMIT


def _validate_token(raw_token: Any) -> str:
    if not isinstance(raw_token, str) or not raw_token.strip():
        raise DiscordSettingsInvalidError("token must be a non-empty string")
    token = raw_token.strip()
    if TOKEN_PATTERN.fullmatch(token) is None:
        raise DiscordSettingsInvalidError(
            "token must not contain spaces, line breaks, or other symbols"
        )
    return token


def _validate_snowflake_id(key: str, raw_id: Any) -> str | None:
    if raw_id is None or raw_id == "":
        return None
    if not is_snowflake(raw_id):
        raise DiscordSettingsInvalidError(
            f"{key} must be a 17 to 20 digit string, or null to clear"
        )
    return raw_id


def _validate_template(raw_template: Any) -> str:
    if not isinstance(raw_template, str) or not raw_template.strip():
        raise DiscordSettingsInvalidError("message_template must be a non-empty string")
    return raw_template


def _validate_max_chars(raw_max_chars: Any) -> int:
    if not _is_valid_max_chars(raw_max_chars):
        raise DiscordSettingsInvalidError(
            f"max_chars must be a whole number from 1 to {MAX_CHARS_LIMIT}"
        )
    return raw_max_chars


def _validate_patch(patch: Any) -> dict[str, Any]:
    if not isinstance(patch, dict):
        raise DiscordSettingsInvalidError("settings must be a mapping")
    unknown_keys = sorted(set(patch) - set(SETTINGS_KEYS))
    if unknown_keys:
        raise DiscordSettingsInvalidError(f"not a Discord setting: {', '.join(unknown_keys)}")
    validated_patch: dict[str, Any] = {}
    for setting_key, setting_value in patch.items():
        validated_patch[setting_key] = _validate_setting(setting_key, setting_value)
    return validated_patch


def _validate_setting(setting_key: str, setting_value: Any) -> Any:
    if setting_key == "token":
        return _validate_token(setting_value)
    if setting_key in ID_KEYS:
        return _validate_snowflake_id(setting_key, setting_value)
    if setting_key == "message_template":
        return _validate_template(setting_value)
    return _validate_max_chars(setting_value)


def _build_mongo_update(validated_patch: dict[str, Any]) -> dict[str, Any]:
    changed_settings: dict[str, Any] = {}
    cleared_settings: dict[str, str] = {}
    for setting_key, setting_value in validated_patch.items():
        if setting_value is None:
            cleared_settings[setting_key] = ""
            continue
        changed_settings[setting_key] = setting_value
    mongo_update: dict[str, Any] = {
        "$set": {**changed_settings, "updated_at": datetime.now(UTC).isoformat()}
    }
    if cleared_settings:
        mongo_update["$unset"] = cleared_settings
    return mongo_update
