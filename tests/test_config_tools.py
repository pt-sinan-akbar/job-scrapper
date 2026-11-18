from __future__ import annotations

from copy import deepcopy
from typing import Any

import mongomock
import pytest

from mcp_server import server
from scraper.job_settings import JobSettingsStore

SETTINGS: dict[str, Any] = {
    "sites": {
        "upwork": {
            "enabled": True,
            "limit": 3,
            "url_template": "https://www.upwork.com/nx/search/jobs/?q={keyword}&sort=recency",
        },
        "glints": {
            "enabled": False,
            "limit": 3,
            "url_template": "https://glints.com/id/opportunities/jobs/explore?keyword={keyword}",
        },
    },
}


@pytest.fixture
def database(monkeypatch: pytest.MonkeyPatch) -> Any:
    db = mongomock.MongoClient()["job_scraper"]
    monkeypatch.setattr(server.mongo, "get_database", lambda: db)
    JobSettingsStore(db).seed(deepcopy(SETTINGS))
    return db


def test_get_config_returns_settings_with_version(database: Any):
    result = server.get_config()

    assert result["version"] == 1
    assert result["updated_by"] == "seed"
    assert result["settings"] == SETTINGS


def test_get_config_lists_job_fields_and_the_always_saved_ones(database: Any):
    result = server.get_config()

    assert result["job_fields"][:3] == ["site", "matched_keyword", "title"]
    assert result["job_fields"][-1] == "requirements"
    assert {"salary_min", "salary_max", "company_id"} <= set(result["job_fields"])
    assert result["mandatory_fields"] == ["site", "matched_keyword", "title", "company", "url"]


def test_get_config_lists_city_options_for_sites_with_a_picker(database: Any):
    options = server.get_config()["location_options"]

    assert set(options) == {"jobstreet", "glints", "linkedin"}
    assert options["jobstreet"][0] == {"label": "Jakarta", "value": "Jakarta Raya"}


def test_get_config_reports_missing_document(monkeypatch: pytest.MonkeyPatch):
    db = mongomock.MongoClient()["job_scraper"]
    monkeypatch.setattr(server.mongo, "get_database", lambda: db)

    assert "seed.sh" in server.get_config()["error"]


UPWORK_LIMIT_9 = {"sites": {"upwork": {"limit": 9}}}


def test_update_config_saves_patch(database: Any):
    result = server.update_config(UPWORK_LIMIT_9, expected_version=1, source="ui")

    assert result["ok"] is True
    assert result["version"] == 2
    assert result["settings"]["sites"]["upwork"]["limit"] == 9
    assert server.get_config()["updated_by"] == "ui"


def test_update_config_saves_site_age_and_filter(database: Any):
    patch = {"sites": {"upwork": {"max_age_hours": 24, "filter": {"work_type": ["remote"]}}}}

    result = server.update_config(patch, expected_version=1)

    assert result["ok"] is True
    assert result["settings"]["sites"]["upwork"]["max_age_hours"] == 24
    assert result["settings"]["sites"]["upwork"]["filter"] == {"work_type": ["remote"]}


@pytest.mark.parametrize("key", ["limit", "concurrency", "max_age_hours", "filter"])
def test_update_config_refuses_global_job_values(database: Any, key: str):
    result = server.update_config({key: 3}, expected_version=1)

    assert result["ok"] is False
    assert result["reason"] == "invalid"
    assert f"not a job setting: {key}" in result["message"]
    assert server.get_config()["version"] == 1


def test_list_sites_has_no_global_limit(database: Any, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PROXY_URL", "")

    result = server.list_sites()

    assert "limit" not in result
    assert [site["name"] for site in result["sites"]] == ["upwork", "glints"]


def test_list_sites_has_no_keywords_and_samples_a_neutral_keyword(
    database: Any, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("PROXY_URL", "")

    result = server.list_sites()

    assert set(result) == {"sites"}
    assert result["sites"][0]["sample_url"] == (
        "https://www.upwork.com/nx/search/jobs/?q=data%20analyst&sort=recency"
    )


def test_update_config_refuses_keywords(database: Any):
    result = server.update_config({"keywords": ["qa"]})

    assert result["ok"] is False
    assert result["reason"] == "invalid"
    assert "not a job setting: keywords" in result["message"]


def test_update_config_reports_conflict(database: Any):
    result = server.update_config(UPWORK_LIMIT_9, expected_version=5)

    assert result["ok"] is False
    assert result["reason"] == "conflict"


def test_update_config_reports_invalid_patch(database: Any):
    result = server.update_config({"sites": {"upwork": {"limit": 0}}})

    assert result["ok"] is False
    assert result["reason"] == "invalid"
    assert "sites.upwork.limit" in result["message"]


@pytest.mark.parametrize(
    "patch",
    [
        {"default_fields": ["title", "salary_mni"]},
        {"sites": {"upwork": {"fields": ["salary_mni"]}}},
    ],
)
def test_update_config_refuses_unknown_job_fields(database: Any, patch: dict[str, Any]):
    result = server.update_config(patch, expected_version=1)

    assert result["ok"] is False
    assert result["reason"] == "invalid"
    assert "salary_mni" in result["message"]
    assert server.get_config()["version"] == 1


def test_update_config_reports_non_text_job_fields_as_invalid(database: Any):
    result = server.update_config({"default_fields": [["title"]]}, expected_version=1)

    assert result["ok"] is False
    assert result["reason"] == "invalid"


def test_update_config_saves_known_job_fields(database: Any):
    patch = {"default_fields": ["salary_min"], "sites": {"upwork": {"fields": []}}}

    result = server.update_config(patch, expected_version=1)

    assert result["ok"] is True
    assert result["settings"]["default_fields"] == ["salary_min"]


def test_update_config_refuses_proxy(database: Any):
    result = server.update_config({"proxy": "socks5://localhost:1080"})

    assert result["ok"] is False
    assert result["reason"] == "invalid"


def test_update_config_reports_missing_document(monkeypatch: pytest.MonkeyPatch):
    db = mongomock.MongoClient()["job_scraper"]
    monkeypatch.setattr(server.mongo, "get_database", lambda: db)

    result = server.update_config(UPWORK_LIMIT_9)

    assert result["ok"] is False
    assert result["reason"] == "unavailable"


def test_history_tools_are_gone():
    assert not hasattr(server, "get_config_history")
    assert not hasattr(server, "restore_config")
