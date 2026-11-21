from __future__ import annotations

from copy import deepcopy
from typing import Any
from unittest.mock import MagicMock

import mongomock
import pytest
from pymongo.errors import ServerSelectionTimeoutError

from scraper import job_settings
from scraper.config_loader import PROXY_ENV_VAR, ConfigError, validate_job_settings
from scraper.job_settings import (
    BACKUP_ID,
    SETTINGS_COLLECTION,
    SETTINGS_ID,
    JobSettingsStore,
    SettingsConflictError,
    SettingsMigrationError,
    SettingsMissingError,
    SettingsUnavailableError,
    load_app_config,
    merge_settings,
    migrate_legacy_settings,
)

UPWORK_URL = "https://www.upwork.com/nx/search/jobs/?q={keyword}&sort=recency"
GLINTS_URL = "https://glints.com/id/opportunities/jobs/explore?keyword={keyword}"
JOBSTREET_URL = "https://id.jobstreet.com/id/{keyword_slug}-jobs"
SETTINGS: dict[str, Any] = {
    "sites": {
        "upwork": {
            "enabled": True,
            "limit": 30,
            "max_age_hours": 72,
            "filter": {},
            "url_template": UPWORK_URL,
        },
        "glints": {
            "enabled": False,
            "limit": 2,
            "filter": {"location": ["jakarta"]},
            "url_template": GLINTS_URL,
        },
    },
}
LEGACY: dict[str, Any] = {
    "keywords": ["devops"],
    "limit": 5,
    "concurrency": 4,
    "max_age_hours": 72,
    "filter": {"location": ["jakarta"]},
    "sites": {
        "jobstreet": {"url_template": JOBSTREET_URL},
        "upwork": {"limit": 30, "filter": {}, "url_template": UPWORK_URL},
        "glints": {"limit": 2, "max_age_hours": 24, "url_template": GLINTS_URL},
    },
}
LEGACY_VERSION = 3


def _upwork_limit(value: int | None) -> dict[str, Any]:
    return {"sites": {"upwork": {"limit": value}}}


@pytest.fixture
def store() -> JobSettingsStore:
    job_store = JobSettingsStore(mongomock.MongoClient()["job_scraper"])
    assert job_store.seed(deepcopy(SETTINGS)) is True
    return job_store


def test_merge_replaces_top_level_keys():
    merged = merge_settings(SETTINGS, {"fields": ["title"]})

    assert merged["fields"] == ["title"]
    assert merged["sites"] == SETTINGS["sites"]


def test_merge_replaces_site_filter_whole():
    merged = merge_settings(SETTINGS, {"sites": {"glints": {"filter": {"work_type": ["remote"]}}}})

    assert merged["sites"]["glints"]["filter"] == {"work_type": ["remote"]}
    assert merged["sites"]["glints"]["limit"] == 2


def test_merge_changes_one_site_and_keeps_the_rest():
    merged = merge_settings(SETTINGS, {"sites": {"upwork": {"limit": 9}}})

    assert merged["sites"]["upwork"]["limit"] == 9
    assert merged["sites"]["upwork"]["url_template"] == UPWORK_URL
    assert merged["sites"]["glints"] == SETTINGS["sites"]["glints"]


def test_merge_replaces_site_filter_with_empty_filter():
    merged = merge_settings(SETTINGS, {"sites": {"glints": {"filter": {}}}})

    assert merged["sites"]["glints"]["filter"] == {}


def test_merge_removes_site_field_on_none():
    merged = merge_settings(SETTINGS, {"sites": {"upwork": {"max_age_hours": None}}})

    assert "max_age_hours" not in merged["sites"]["upwork"]


def test_merge_does_not_change_input():
    original = deepcopy(SETTINGS)

    merge_settings(SETTINGS, {"fields": ["title"], "sites": {"upwork": {"limit": 1}}})

    assert original == SETTINGS


def test_merge_rejects_site_that_is_not_a_mapping():
    with pytest.raises(ConfigError, match="sites.upwork must be a mapping"):
        merge_settings(SETTINGS, {"sites": {"upwork": 3}})


def test_merge_rejects_sites_that_is_not_a_mapping():
    with pytest.raises(ConfigError, match="'sites' must be a mapping"):
        merge_settings(SETTINGS, {"sites": None})


def test_read_returns_seeded_settings(store: JobSettingsStore):
    stored = store.read()

    assert stored.version == 1
    assert stored.updated_by == "seed"
    assert stored.settings == SETTINGS


def test_read_reports_missing_document():
    store = JobSettingsStore(mongomock.MongoClient()["job_scraper"])

    with pytest.raises(SettingsMissingError, match="seed.sh job-settings"):
        store.read()


def test_seed_keeps_existing_document(store: JobSettingsStore):
    store.save(_upwork_limit(9), 1, "ui")

    assert store.seed(deepcopy(SETTINGS)) is False
    assert store.read().settings["sites"]["upwork"]["limit"] == 9


def test_seed_after_lost_document_starts_at_first_version():
    database = mongomock.MongoClient()["job_scraper"]
    lost = JobSettingsStore(database)
    lost.seed(deepcopy(SETTINGS))
    lost.save(_upwork_limit(5), None, "ui")
    database[SETTINGS_COLLECTION].delete_one({"_id": SETTINGS_ID})

    assert lost.seed(deepcopy(SETTINGS)) is True
    assert lost.read().version == 1
    assert lost.save(_upwork_limit(7), None, "ui").version == 2


def test_seed_rejects_invalid_settings():
    store = JobSettingsStore(mongomock.MongoClient()["job_scraper"])

    with pytest.raises(ConfigError):
        store.seed({"sites": {}})


def test_seed_refuses_global_job_values():
    store = JobSettingsStore(mongomock.MongoClient()["job_scraper"])

    with pytest.raises(ConfigError, match="not a job setting: limit"):
        store.seed({**deepcopy(SETTINGS), "limit": 3})


def test_seed_refuses_global_keywords():
    store = JobSettingsStore(mongomock.MongoClient()["job_scraper"])

    with pytest.raises(ConfigError, match="not a job setting: keywords"):
        store.seed({**deepcopy(SETTINGS), "keywords": ["devops"]})


def test_save_moves_to_next_version(store: JobSettingsStore):
    saved = store.save(_upwork_limit(9), 1, "ui")

    assert saved.version == 2
    assert saved.updated_by == "ui"
    assert store.read().version == 2
    assert store.read().settings["sites"]["upwork"]["limit"] == 9


def test_save_writes_only_the_live_document():
    database = mongomock.MongoClient()["job_scraper"]
    store = JobSettingsStore(database)
    store.seed(deepcopy(SETTINGS))

    store.save(_upwork_limit(9), 1, "ui")

    assert database.list_collection_names() == [SETTINGS_COLLECTION]
    assert database[SETTINGS_COLLECTION].count_documents({}) == 1


def test_save_rejects_stale_version(store: JobSettingsStore):
    store.save(_upwork_limit(9), 1, "ui")

    with pytest.raises(SettingsConflictError):
        store.save(_upwork_limit(10), 1, "ui")

    assert store.read().settings["sites"]["upwork"]["limit"] == 9


def test_save_detects_a_write_between_read_and_update(
    store: JobSettingsStore, monkeypatch: pytest.MonkeyPatch
):
    stale = store.read()
    store.save(_upwork_limit(9), None, "ui")
    monkeypatch.setattr(store, "read", lambda: stale)

    with pytest.raises(SettingsConflictError):
        store.save(_upwork_limit(10), None, "ui")


def test_save_leaves_document_unchanged_when_invalid(store: JobSettingsStore):
    with pytest.raises(ConfigError):
        store.save(_upwork_limit(0), 1, "ui")

    assert store.read().version == 1
    assert store.read().settings["sites"]["upwork"]["limit"] == 30


@pytest.mark.parametrize("key", ["limit", "concurrency", "max_age_hours", "filter", "keywords"])
def test_save_refuses_global_job_values(store: JobSettingsStore, key: str):
    with pytest.raises(ConfigError, match=f"not a job setting: {key}"):
        store.save({key: 3}, 1, "ui")

    assert store.read().version == 1


def test_save_refuses_default_fields(store: JobSettingsStore):
    with pytest.raises(ConfigError, match="not a job setting: default_fields"):
        store.save({"default_fields": ["title"]}, 1, "ui")

    assert store.read().version == 1


def test_save_refuses_site_fields(store: JobSettingsStore):
    with pytest.raises(ConfigError, match="sites.upwork.fields is no longer supported"):
        store.save({"sites": {"upwork": {"fields": ["title"]}}}, 1, "ui")

    assert store.read().version == 1


def test_save_refuses_unknown_names_in_fields(store: JobSettingsStore):
    with pytest.raises(ConfigError, match="unknown job fields: salary_mni"):
        store.save({"fields": ["title", "salary_mni"]}, 1, "ui")

    assert store.read().version == 1


def test_save_stores_top_level_fields(store: JobSettingsStore):
    saved = store.save({"fields": ["title", "salary"]}, 1, "ui")

    assert saved.settings["fields"] == ["title", "salary"]


def test_save_refuses_removing_a_site_limit(store: JobSettingsStore):
    with pytest.raises(ConfigError, match="sites.upwork.limit is required"):
        store.save(_upwork_limit(None), 1, "ui")


def test_store_has_no_history_or_restore(store: JobSettingsStore):
    assert not hasattr(store, "history")
    assert not hasattr(store, "restore")


def test_mongo_failure_hides_connection_details():
    database = MagicMock()
    database.__getitem__.return_value.find_one.side_effect = ServerSelectionTimeoutError(
        "secret-host:27017"
    )

    with pytest.raises(SettingsUnavailableError) as caught:
        JobSettingsStore(database).read()

    assert "secret-host" not in str(caught.value)


def test_load_app_config_joins_store_and_proxy(
    store: JobSettingsStore, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv(PROXY_ENV_VAR, "socks5://localhost:1080")

    config = load_app_config(store)
    upwork = config.find_site_config("upwork")

    assert not hasattr(config, "keywords")
    assert config.proxy is not None
    assert config.proxy.url == "socks5://localhost:1080"
    assert upwork is not None
    assert upwork.filter == {}
    assert upwork.limit == 30


def test_load_app_config_stops_when_proxy_is_unset(
    store: JobSettingsStore, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv(PROXY_ENV_VAR, raising=False)

    with pytest.raises(ConfigError, match=PROXY_ENV_VAR):
        load_app_config(store)


def _legacy_database(settings: dict[str, Any] | None = None) -> Any:
    database = mongomock.MongoClient()["job_scraper"]
    database[SETTINGS_COLLECTION].insert_one(
        {
            "_id": SETTINGS_ID,
            "version": LEGACY_VERSION,
            "settings": deepcopy(settings if settings is not None else LEGACY),
            "updated_at": "2026-11-01T00:00:00+00:00",
            "updated_by": "ui",
        }
    )
    return database


def test_migration_moves_global_values_into_sites():
    sites = migrate_legacy_settings(LEGACY)["sites"]

    assert sites["jobstreet"] == {
        "url_template": JOBSTREET_URL,
        "limit": 5,
        "max_age_hours": 72,
        "filter": {"location": ["jakarta"]},
    }
    assert sites["upwork"] == {
        "limit": 30,
        "filter": {},
        "max_age_hours": 72,
        "url_template": UPWORK_URL,
    }
    assert sites["glints"] == {
        "limit": 2,
        "max_age_hours": 24,
        "filter": {"location": ["jakarta"]},
        "url_template": GLINTS_URL,
    }


def test_migration_drops_the_global_keys_and_keeps_the_rest():
    migrated = migrate_legacy_settings(LEGACY)

    assert set(migrated) == {"sites"}
    validate_job_settings(migrated)


def test_migration_falls_back_to_limit_2_and_skips_empty_globals():
    legacy = {
        "keywords": ["devops"],
        "concurrency": 4,
        "max_age_hours": None,
        "filter": {},
        "sites": {"jobstreet": {"url_template": JOBSTREET_URL, "limit": None}},
    }

    migrated = migrate_legacy_settings(legacy)

    assert migrated["sites"]["jobstreet"] == {"url_template": JOBSTREET_URL, "limit": 2}


def test_migration_leaves_current_settings_alone():
    assert migrate_legacy_settings(SETTINGS) == SETTINGS


def test_migration_drops_global_keywords_and_leaves_sites_alone():
    legacy = {**deepcopy(SETTINGS), "keywords": ["devops"], "fields": ["title"]}

    migrated = migrate_legacy_settings(legacy)

    assert migrated == {**SETTINGS, "fields": ["title"]}
    validate_job_settings(migrated)


def test_read_drops_stored_keywords_once():
    database = _legacy_database({**deepcopy(SETTINGS), "keywords": ["devops"]})
    store = JobSettingsStore(database)

    first = store.read()
    second = store.read()
    document = database[SETTINGS_COLLECTION].find_one({"_id": SETTINGS_ID})

    assert first.version == LEGACY_VERSION + 1
    assert first.updated_by == "migration"
    assert "keywords" not in first.settings
    assert second == first
    assert "keywords" not in document["settings"]
    assert document["version"] == LEGACY_VERSION + 1


def test_save_works_after_keywords_are_dropped():
    store = JobSettingsStore(_legacy_database({**deepcopy(SETTINGS), "keywords": ["devops"]}))
    migrated = store.read()

    saved = store.save(_upwork_limit(9), migrated.version, "ui")

    assert saved.version == LEGACY_VERSION + 2
    assert "keywords" not in saved.settings


def test_migration_does_not_change_input():
    original = deepcopy(LEGACY)

    migrate_legacy_settings(LEGACY)

    assert original == LEGACY


def test_read_migrates_and_stores_the_settings_once():
    database = _legacy_database()
    store = JobSettingsStore(database)

    stored = store.read()
    document = database[SETTINGS_COLLECTION].find_one({"_id": SETTINGS_ID})

    assert stored.version == LEGACY_VERSION + 1
    assert stored.updated_by == "migration"
    assert stored.settings == migrate_legacy_settings(LEGACY)
    assert document["version"] == LEGACY_VERSION + 1
    assert document["settings"] == stored.settings


def test_read_after_migration_changes_nothing():
    database = _legacy_database()
    store = JobSettingsStore(database)
    first = store.read()

    second = store.read()

    assert second == first
    assert database[SETTINGS_COLLECTION].count_documents({"_id": SETTINGS_ID}) == 1


def test_migration_logs_once(monkeypatch: pytest.MonkeyPatch):
    logger = MagicMock()
    monkeypatch.setattr(job_settings, "_LOG", logger)
    store = JobSettingsStore(_legacy_database())

    store.read()
    store.read()

    logger.info.assert_called_once()


class _StaleFirstRead:
    def __init__(self, collection: Any) -> None:
        self._collection = collection
        self._stale = [collection.find_one({"_id": SETTINGS_ID})]

    def find_one(self, *args: Any, **kwargs: Any) -> Any:
        return self._stale.pop() if self._stale else self._collection.find_one(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._collection, name)


def test_two_processes_migrating_at_once_store_one_version():
    database = _legacy_database()
    collection = database[SETTINGS_COLLECTION]
    late = JobSettingsStore({SETTINGS_COLLECTION: _StaleFirstRead(collection)})
    early_result = JobSettingsStore(database).read()

    late_result = late.read()

    assert late_result == early_result
    assert collection.find_one({"_id": SETTINGS_ID})["version"] == LEGACY_VERSION + 1


def test_save_works_after_migration():
    store = JobSettingsStore(_legacy_database())
    migrated = store.read()

    saved = store.save({"sites": {"jobstreet": {"limit": 7}}}, migrated.version, "ui")

    assert saved.version == LEGACY_VERSION + 2
    assert store.read().settings["sites"]["jobstreet"]["limit"] == 7
    assert store.read().settings["sites"]["jobstreet"]["max_age_hours"] == 72


def test_save_with_a_version_from_before_migration_is_a_conflict():
    store = JobSettingsStore(_legacy_database())

    with pytest.raises(SettingsConflictError):
        store.save({"sites": {"jobstreet": {"limit": 7}}}, LEGACY_VERSION, "ui")


def test_load_app_config_reads_migrated_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(PROXY_ENV_VAR, "")

    config = load_app_config(JobSettingsStore(_legacy_database()))
    jobstreet = config.find_site_config("jobstreet")

    assert jobstreet is not None
    assert jobstreet.limit == 5
    assert jobstreet.max_age_hours == 72
    assert jobstreet.filter == {"location": ["jakarta"]}


def _active(database: Any) -> dict[str, Any]:
    return database[SETTINGS_COLLECTION].find_one({"_id": SETTINGS_ID})


def _backup(database: Any) -> dict[str, Any] | None:
    return database[SETTINGS_COLLECTION].find_one({"_id": BACKUP_ID})


def test_migration_clamps_site_limits_to_1_to_200():
    legacy = {
        "limit": 5,
        "sites": {
            "upwork": {"limit": 500, "url_template": UPWORK_URL},
            "glints": {"limit": 0, "url_template": GLINTS_URL},
        },
    }

    sites = migrate_legacy_settings(legacy)["sites"]

    assert sites["upwork"]["limit"] == 200
    assert sites["glints"]["limit"] == 1


def test_migration_replaces_a_site_limit_of_the_wrong_type_with_the_fallback():
    legacy = {"limit": "five", "sites": {"upwork": {"limit": "9", "url_template": UPWORK_URL}}}

    migrated = migrate_legacy_settings(legacy)

    assert migrated["sites"]["upwork"]["limit"] == 2
    validate_job_settings(migrated)


def test_migration_clamps_the_global_limit_it_copies():
    legacy = {"limit": 900, "sites": {"jobstreet": {"url_template": JOBSTREET_URL}}}

    assert migrate_legacy_settings(legacy)["sites"]["jobstreet"]["limit"] == 200


def test_migration_drops_global_max_age_and_filter_of_the_wrong_type():
    legacy = {
        "max_age_hours": "soon",
        "filter": ["jakarta"],
        "sites": {"upwork": {"limit": 4, "url_template": UPWORK_URL}},
    }

    migrated = migrate_legacy_settings(legacy)

    assert migrated["sites"]["upwork"] == {"limit": 4, "url_template": UPWORK_URL}
    validate_job_settings(migrated)


def test_migration_fills_missing_limits_when_only_keywords_are_legacy():
    legacy = {"keywords": ["devops"], "sites": {"jobstreet": {"url_template": JOBSTREET_URL}}}

    migrated = migrate_legacy_settings(legacy)

    assert migrated == {"sites": {"jobstreet": {"url_template": JOBSTREET_URL, "limit": 2}}}
    validate_job_settings(migrated)


def test_read_stores_a_valid_document_for_a_keywords_only_legacy_doc():
    database = _legacy_database(
        {"keywords": ["devops"], "sites": {"jobstreet": {"url_template": JOBSTREET_URL}}}
    )

    stored = JobSettingsStore(database).read()

    validate_job_settings(_active(database)["settings"])
    assert stored.settings["sites"]["jobstreet"]["limit"] == 2


def test_read_refuses_a_migration_that_stays_invalid_and_keeps_the_document():
    broken = {
        "limit": 5,
        "sites": {"upwork": {"url_template": "https://evil.example.com/{keyword}"}},
    }
    database = _legacy_database(broken)
    store = JobSettingsStore(database)

    with pytest.raises(SettingsMigrationError, match="evil.example.com"):
        store.read()

    document = _active(database)
    assert document["version"] == LEGACY_VERSION
    assert document["settings"] == broken
    assert _backup(database) is None


def test_migration_error_is_a_config_error():
    assert issubclass(SettingsMigrationError, ConfigError)


def test_read_keeps_a_backup_of_the_document_before_migration():
    database = _legacy_database()

    JobSettingsStore(database).read()
    backup = _backup(database)

    assert backup is not None
    assert backup["version"] == LEGACY_VERSION
    assert backup["settings"] == LEGACY
    assert backup["updated_by"] == "ui"
    assert backup["updated_at"] == "2026-11-01T00:00:00+00:00"


def test_backup_from_an_earlier_migration_is_never_replaced():
    database = _legacy_database()
    earlier = {"_id": BACKUP_ID, "version": 1, "settings": {"limit": 1}}
    database[SETTINGS_COLLECTION].insert_one(earlier)

    JobSettingsStore(database).read()

    assert _backup(database) == earlier


def test_backup_does_not_change_reads_saves_or_seed():
    database = _legacy_database()
    store = JobSettingsStore(database)
    migrated = store.read()

    saved = store.save(_upwork_limit(9), migrated.version, "ui")

    assert store.seed(deepcopy(SETTINGS)) is False
    assert store.read() == saved
    backup = _backup(database)
    assert backup is not None
    assert backup["settings"] == LEGACY


def test_migration_logs_the_sites_that_got_the_fallback_limit(monkeypatch: pytest.MonkeyPatch):
    logger = MagicMock()
    monkeypatch.setattr(job_settings, "_LOG", logger)
    legacy = {
        "keywords": ["devops"],
        "sites": {
            "jobstreet": {"url_template": JOBSTREET_URL},
            "upwork": {"limit": 4, "url_template": UPWORK_URL},
        },
    }

    JobSettingsStore(_legacy_database(legacy)).read()

    logger.warning.assert_called_once()
    message = logger.warning.call_args.args[0] % logger.warning.call_args.args[1:]
    assert "jobstreet" in message
    assert "upwork" not in message
    assert "2" in message


def test_migration_without_fallback_logs_no_warning(monkeypatch: pytest.MonkeyPatch):
    logger = MagicMock()
    monkeypatch.setattr(job_settings, "_LOG", logger)

    JobSettingsStore(_legacy_database()).read()

    logger.warning.assert_not_called()


def test_migration_renames_default_fields_to_fields():
    legacy = {**deepcopy(SETTINGS), "default_fields": ["title", "salary"]}

    migrated = migrate_legacy_settings(legacy)

    assert migrated == {**SETTINGS, "fields": ["title", "salary"]}
    validate_job_settings(migrated)


def test_migration_keeps_fields_when_default_fields_is_also_stored():
    legacy = {**deepcopy(SETTINGS), "default_fields": ["title"], "fields": ["salary"]}

    migrated = migrate_legacy_settings(legacy)

    assert migrated["fields"] == ["salary"]
    assert "default_fields" not in migrated


def test_migration_keeps_an_empty_default_fields_list():
    legacy = {**deepcopy(SETTINGS), "default_fields": []}

    assert migrate_legacy_settings(legacy)["fields"] == []


def test_migration_drops_site_fields_and_keeps_the_rest_of_the_site():
    legacy = deepcopy(SETTINGS)
    legacy["sites"]["upwork"]["fields"] = ["title"]

    migrated = migrate_legacy_settings(legacy)

    assert migrated == SETTINGS
    validate_job_settings(migrated)


def test_site_fields_alone_count_as_legacy():
    legacy = deepcopy(SETTINGS)
    legacy["sites"]["glints"]["fields"] = None

    assert job_settings.has_legacy_globals(legacy) is True
    assert job_settings.list_sites_with_fields_override(legacy) == ("glints",)


def test_read_stores_migrated_fields_once():
    legacy = {**deepcopy(SETTINGS), "default_fields": ["title", "salary"]}
    legacy["sites"]["upwork"]["fields"] = ["title"]
    database = _legacy_database(legacy)
    store = JobSettingsStore(database)

    first = store.read()
    second = store.read()
    document = _active(database)

    assert first.version == LEGACY_VERSION + 1
    assert first.settings == {**SETTINGS, "fields": ["title", "salary"]}
    assert second == first
    backup = _backup(database)
    assert document["settings"] == first.settings
    assert backup is not None
    assert backup["settings"] == legacy


def test_load_app_config_uses_migrated_default_fields(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(PROXY_ENV_VAR, "")
    legacy = {**deepcopy(SETTINGS), "default_fields": ["salary"]}

    config = load_app_config(JobSettingsStore(_legacy_database(legacy)))

    assert config.fields == ("salary",)


def test_migration_logs_the_sites_that_lost_their_fields(monkeypatch: pytest.MonkeyPatch):
    logger = MagicMock()
    monkeypatch.setattr(job_settings, "_LOG", logger)
    legacy = deepcopy(SETTINGS)
    legacy["sites"]["upwork"]["fields"] = ["title"]

    JobSettingsStore(_legacy_database(legacy)).read()

    logger.warning.assert_called_once()
    message = logger.warning.call_args.args[0] % logger.warning.call_args.args[1:]
    assert "upwork" in message
    assert "glints" not in message
    info_message = logger.info.call_args.args[0] % logger.info.call_args.args[1:]
    assert "sites.upwork.fields" in info_message


def test_migration_of_default_fields_logs_no_warning(monkeypatch: pytest.MonkeyPatch):
    logger = MagicMock()
    monkeypatch.setattr(job_settings, "_LOG", logger)
    legacy = {**deepcopy(SETTINGS), "default_fields": ["title"]}

    JobSettingsStore(_legacy_database(legacy)).read()

    logger.warning.assert_not_called()
    logger.info.assert_called_once()
