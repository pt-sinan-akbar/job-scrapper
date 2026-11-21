from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any

from pymongo import MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError

from .config_loader import (
    MAX_SITE_LIMIT,
    AppConfig,
    ConfigError,
    is_valid_max_age,
    parse_job_settings_into_app_config,
    read_proxy_url_from_env,
    validate_job_settings,
)
from .log import get_scraper_logger
from .types import CANONICAL_FIELDS

_LOG = get_scraper_logger()

SETTINGS_COLLECTION = "job_settings"
SETTINGS_ID = "active"
BACKUP_ID = "active_pre_migration_backup"
SOURCE_SEED = "seed"
SOURCE_MIGRATION = "migration"
FIRST_VERSION = 1
LEGACY_GLOBAL_KEYS: tuple[str, ...] = ("limit", "concurrency", "max_age_hours", "filter")
LEGACY_DROPPED_KEYS: tuple[str, ...] = ("keywords",)
LEGACY_FIELDS_KEY = "default_fields"
FIELDS_KEY = "fields"
LEGACY_KEYS: tuple[str, ...] = LEGACY_GLOBAL_KEYS + LEGACY_DROPPED_KEYS + (LEGACY_FIELDS_KEY,)
LEGACY_FALLBACK_LIMIT = 2
CONFLICT_MESSAGE = "These settings changed somewhere else. Reload and try again"


class SettingsMissingError(ConfigError):
    pass


class SettingsConflictError(ConfigError):
    pass


class SettingsUnavailableError(ConfigError):
    pass


class SettingsMigrationError(ConfigError):
    pass


@dataclass(frozen=True)
class StoredSettings:
    version: int
    settings: dict[str, Any]
    updated_at: str
    updated_by: str


def _to_stored(document: dict[str, Any]) -> StoredSettings:
    return StoredSettings(
        version=document["version"],
        settings=document["settings"],
        updated_at=document["updated_at"],
        updated_by=document["updated_by"],
    )


def _stamp(settings: dict[str, Any], version: int, source: str) -> dict[str, Any]:
    return {
        "version": version,
        "settings": settings,
        "updated_at": datetime.now(UTC).isoformat(),
        "updated_by": source,
    }


def _apply_fields(current: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    kept = {key: value for key, value in current.items() if key not in patch}
    changed = {key: value for key, value in patch.items() if value is not None}
    return {**kept, **changed}


def _merge_site(current: dict[str, Any], name: str, patch: Any) -> dict[str, Any]:
    if not isinstance(patch, dict):
        raise ConfigError(f"sites.{name} must be a mapping")
    return _apply_fields(current.get(name, {}), patch)


def _unknown_fields(fields: Any) -> list[str]:
    if not isinstance(fields, list):
        return []
    # Non-text entries are left to validate_job_settings, which reports them clearly
    return [field for field in fields if isinstance(field, str) and field not in CANONICAL_FIELDS]


def _refuse_unknown_fields(patch: dict[str, Any]) -> None:
    """Refuse job field names the scraper does not know, so they are never stored.

    Stored settings stay lenient: the loader skips unknown
    names with a warning, so older data keeps working.
    """
    unknown = _unknown_fields(patch.get(FIELDS_KEY))
    if unknown:
        raise ConfigError(f"unknown job fields: {', '.join(sorted(set(unknown)))}")


def merge_settings(current: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = _apply_fields(current, {k: v for k, v in patch.items() if k != "sites"})
    if "sites" not in patch:
        return merged
    site_patches = patch["sites"]
    if not isinstance(site_patches, dict):
        raise ConfigError("'sites' must be a mapping")
    sites = current.get("sites", {})
    changed = {name: _merge_site(sites, name, fields) for name, fields in site_patches.items()}
    return {**merged, "sites": {**sites, **changed}}


def has_legacy_globals(settings: dict[str, Any]) -> bool:
    if any(key in settings for key in LEGACY_KEYS):
        return True
    return bool(list_sites_with_fields_override(settings))


def list_sites_with_fields_override(settings: dict[str, Any]) -> tuple[str, ...]:
    sites = settings.get("sites")
    if not isinstance(sites, dict):
        return ()
    site_names: list[str] = []
    for name, site in sites.items():
        if isinstance(site, dict) and FIELDS_KEY in site:
            site_names.append(name)
    return tuple(site_names)


def _is_whole(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _usable_limit(value: Any) -> int | None:
    return max(1, min(MAX_SITE_LIMIT, value)) if _is_whole(value) else None


def _fallback_limit(legacy: dict[str, Any]) -> int:
    global_limit = _usable_limit(legacy.get("limit"))
    return global_limit if global_limit is not None else LEGACY_FALLBACK_LIMIT


def _copied_globals(site: dict[str, Any], legacy: dict[str, Any]) -> dict[str, Any]:
    max_age = legacy.get("max_age_hours")
    global_filter = legacy.get("filter")
    copy_max_age = (
        max_age is not None and site.get("max_age_hours") is None and is_valid_max_age(max_age)
    )
    copy_filter = isinstance(global_filter, dict) and bool(global_filter) and "filter" not in site
    return {
        **({"max_age_hours": max_age} if copy_max_age else {}),
        **({"filter": global_filter} if copy_filter else {}),
    }


def _drop_site_fields_override(site: dict[str, Any]) -> dict[str, Any]:
    site_without_fields: dict[str, Any] = {}
    for key, value in site.items():
        if key == FIELDS_KEY:
            continue
        site_without_fields[key] = value
    return site_without_fields


def _migrate_site(site: Any, legacy: dict[str, Any]) -> Any:
    if not isinstance(site, dict):
        return site
    limit = _usable_limit(site.get("limit"))
    return {
        **_drop_site_fields_override(site),
        "limit": limit if limit is not None else _fallback_limit(legacy),
        **_copied_globals(site, legacy),
    }


def _rename_default_fields(kept: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    if FIELDS_KEY in settings:
        return kept
    legacy_fields = settings.get(LEGACY_FIELDS_KEY)
    if legacy_fields is None:
        return kept
    return {**kept, FIELDS_KEY: legacy_fields}


def migrate_legacy_settings(settings: dict[str, Any]) -> dict[str, Any]:
    if not has_legacy_globals(settings):
        return settings
    kept = {key: value for key, value in settings.items() if key not in LEGACY_KEYS}
    kept_with_fields = _rename_default_fields(kept, settings)
    sites = settings.get("sites")
    if not isinstance(sites, dict):
        return kept_with_fields
    legacy = {key: settings.get(key) for key in LEGACY_GLOBAL_KEYS}
    migrated_sites = {name: _migrate_site(site, legacy) for name, site in sites.items()}
    return {**kept_with_fields, "sites": migrated_sites}


def legacy_fallback_sites(settings: dict[str, Any]) -> tuple[str, ...]:
    sites = settings.get("sites")
    if not has_legacy_globals(settings) or not isinstance(sites, dict):
        return ()
    if _usable_limit(settings.get("limit")) is not None:
        return ()
    return tuple(
        name
        for name, site in sites.items()
        if isinstance(site, dict) and _usable_limit(site.get("limit")) is None
    )


def _validated_migration(settings: dict[str, Any]) -> dict[str, Any]:
    migrated = migrate_legacy_settings(settings)
    try:
        validate_job_settings(migrated)
    except ConfigError as exc:
        raise SettingsMigrationError(
            f"The stored job settings could not be migrated and were left unchanged: {exc}"
        ) from exc
    return migrated


def _backup_fields(legacy: StoredSettings) -> dict[str, Any]:
    return {
        "version": legacy.version,
        "settings": legacy.settings,
        "updated_at": legacy.updated_at,
        "updated_by": legacy.updated_by,
        "backed_up_at": datetime.now(UTC).isoformat(),
    }


@contextmanager
def _mongo_errors() -> Iterator[None]:
    try:
        yield
    except PyMongoError as exc:
        # Keep the message short: pymongo errors can name hosts
        raise SettingsUnavailableError(
            f"The job settings store cannot be reached ({type(exc).__name__})"
        ) from exc


def _list_migrated_keys(settings: dict[str, Any]) -> list[str]:
    migrated_keys: list[str] = []
    for key in LEGACY_KEYS:
        if key in settings:
            migrated_keys.append(key)
    for site_name in list_sites_with_fields_override(settings):
        migrated_keys.append(f"sites.{site_name}.fields")
    return migrated_keys


def _log_migration(legacy: StoredSettings) -> None:
    _LOG.info(
        "[settings] migrated legacy %s off the settings (version %d -> %d), backup kept as %s",
        ", ".join(_list_migrated_keys(legacy.settings)),
        legacy.version,
        legacy.version + 1,
        BACKUP_ID,
    )
    fallback = legacy_fallback_sites(legacy.settings)
    if fallback:
        _LOG.warning(
            "[settings] no usable limit on %s, set to the fallback limit %d",
            ", ".join(fallback),
            LEGACY_FALLBACK_LIMIT,
        )
    sites_with_override = list_sites_with_fields_override(legacy.settings)
    if sites_with_override:
        _LOG.warning(
            "[settings] dropped the per-site fields override on %s, "
            "the top-level fields now apply to every site",
            ", ".join(sites_with_override),
        )


class JobSettingsStore:
    def __init__(self, database: Any) -> None:
        self._settings = database[SETTINGS_COLLECTION]

    def read(self) -> StoredSettings:
        stored = self._find()
        if not has_legacy_globals(stored.settings):
            return stored
        migrated = self._store_migration(stored)
        return migrated if migrated is not None else self._find_migrated()

    def _find(self) -> StoredSettings:
        with _mongo_errors():
            document = self._settings.find_one({"_id": SETTINGS_ID})
        if document is None:
            raise SettingsMissingError(
                "Job settings are missing. Run ./seed.sh job-settings for this environment"
            )
        return _to_stored(document)

    def _find_migrated(self) -> StoredSettings:
        stored = self._find()
        if not has_legacy_globals(stored.settings):
            return stored
        return replace(stored, settings=_validated_migration(stored.settings))

    def _store_migration(self, legacy: StoredSettings) -> StoredSettings | None:
        settings = _validated_migration(legacy.settings)
        self._keep_backup(legacy)
        fields = _stamp(settings, legacy.version + 1, SOURCE_MIGRATION)
        if not self._swap(legacy.version, fields):
            return None
        _log_migration(legacy)
        return _to_stored(fields)

    def _keep_backup(self, legacy: StoredSettings) -> None:
        with _mongo_errors():
            try:
                self._settings.update_one(
                    {"_id": BACKUP_ID},
                    {"$setOnInsert": _backup_fields(legacy)},
                    upsert=True,
                )
            except DuplicateKeyError:
                return

    def _swap(self, version: int, fields: dict[str, Any]) -> bool:
        with _mongo_errors():
            previous = self._settings.find_one_and_update(
                {"_id": SETTINGS_ID, "version": version},
                {"$set": fields},
                return_document=ReturnDocument.BEFORE,
            )
        return previous is not None

    def seed(self, settings: dict[str, Any]) -> bool:
        validate_job_settings(settings)
        with _mongo_errors():
            document = {"_id": SETTINGS_ID, **_stamp(settings, FIRST_VERSION, SOURCE_SEED)}
            try:
                self._settings.insert_one(document)
            except DuplicateKeyError:
                return False
        return True

    def save(
        self, patch: dict[str, Any], expected_version: int | None, source: str
    ) -> StoredSettings:
        _refuse_unknown_fields(patch)
        current = self._read_expected(expected_version)
        return self._replace(current, merge_settings(current.settings, patch), source)

    def _read_expected(self, expected_version: int | None) -> StoredSettings:
        current = self.read()
        if expected_version is not None and expected_version != current.version:
            raise SettingsConflictError(CONFLICT_MESSAGE)
        return current

    def _replace(
        self, current: StoredSettings, settings: dict[str, Any], source: str
    ) -> StoredSettings:
        validate_job_settings(settings)
        fields = _stamp(settings, current.version + 1, source)
        if not self._swap(current.version, fields):
            raise SettingsConflictError(CONFLICT_MESSAGE)
        return _to_stored(fields)


def open_store() -> JobSettingsStore:
    uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    db_name = os.environ.get("MONGO_DB_NAME", "job_scraper")
    timeout = int(os.environ.get("MONGO_SERVER_SELECTION_TIMEOUT_MS", "3000"))
    return JobSettingsStore(MongoClient(uri, serverSelectionTimeoutMS=timeout)[db_name])


def load_app_config(store: JobSettingsStore) -> AppConfig:
    return parse_job_settings_into_app_config(store.read().settings, read_proxy_url_from_env())
