from __future__ import annotations

from copy import deepcopy
from typing import Any

import mongomock
import pytest

from mcp_server import server
from scraper.job_settings import JobSettingsStore

SETTINGS: dict[str, Any] = {
    "keywords": ["devops"],
    "limit": 3,
    "sites": {
        "upwork": {
            "enabled": True,
            "url_template": "https://www.upwork.com/nx/search/jobs/?q={keyword}&sort=recency",
        },
        "glints": {
            "enabled": False,
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
    assert result["settings"]["keywords"] == ["devops"]


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


def test_update_config_saves_patch(database: Any):
    result = server.update_config({"limit": 9}, expected_version=1, source="ui")

    assert result["ok"] is True
    assert result["version"] == 2
    assert result["settings"]["limit"] == 9
    assert server.get_config()["updated_by"] == "ui"


@pytest.mark.parametrize("value", [0, 11])
def test_update_config_refuses_concurrency_out_of_range(database: Any, value: int):
    result = server.update_config({"concurrency": value})

    assert result["ok"] is False
    assert result["reason"] == "invalid"
    assert "concurrency" in result["message"]


def test_update_config_saves_concurrency_and_clears_it_back_to_default(
    database: Any, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("PROXY_URL", "")
    saved = server.update_config({"concurrency": 4}, expected_version=1)
    assert saved["settings"]["concurrency"] == 4
    assert server._load_config().concurrency == 4

    cleared = server.update_config({"concurrency": None}, expected_version=2)

    assert "concurrency" not in cleared["settings"]
    assert server._load_config().concurrency == 2


def test_update_config_reports_conflict(database: Any):
    result = server.update_config({"limit": 9}, expected_version=5)

    assert result["ok"] is False
    assert result["reason"] == "conflict"


def test_update_config_reports_invalid_patch(database: Any):
    result = server.update_config({"limit": 0})

    assert result["ok"] is False
    assert result["reason"] == "invalid"
    assert "limit" in result["message"]


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

    result = server.update_config({"limit": 9})

    assert result["ok"] is False
    assert result["reason"] == "unavailable"


def test_history_tools_are_gone():
    assert not hasattr(server, "get_config_history")
    assert not hasattr(server, "restore_config")
