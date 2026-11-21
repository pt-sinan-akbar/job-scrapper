from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType
from typing import Any
from unittest.mock import MagicMock, create_autospec, patch

from scraper.config_loader import AppConfig
from scraper.runner import FilteredAndRawPayloads, RunResult

KEYWORDS = ["devops", "qa"]
SITES = ["glints", "jobstreet"]
FETCH_FAILED = {"error": "fetch failed", "url": "https://example.com", "keyword": "devops"}


def _build_site_payload(keyword: str, titles: list[str]) -> dict[str, Any]:
    return {
        "keyword": keyword,
        "fields": ["title"],
        "max_age_hours": None,
        "filter": None,
        "count": len(titles),
        "jobs": [{"title": title} for title in titles],
        "source": "api",
        "fallback_reason": None,
    }


def _build_payloads(filtered: dict[str, Any]) -> FilteredAndRawPayloads:
    raw = {"keyword": filtered["keyword"], "count": 9, "jobs": [{"title": "raw"}] * 9}
    return FilteredAndRawPayloads(filtered=filtered, raw=raw)


RUN_RESULT = RunResult(
    exit_code=0,
    results=MappingProxyType(
        {
            ("devops", "glints"): _build_payloads(_build_site_payload("devops", ["A", "B"])),
            ("devops", "jobstreet"): _build_payloads(FETCH_FAILED),
            ("qa", "glints"): _build_payloads(_build_site_payload("qa", ["C", "D", "E"])),
            ("qa", "jobstreet"): _build_payloads(_build_site_payload("qa", ["F"])),
        }
    ),
)


def _scrape_two_keywords_on_two_sites(status_path: Path, logger: MagicMock) -> dict[str, Any]:
    from mcp_server.server import scrape_jobs

    config = create_autospec(AppConfig, instance=True)
    with (
        patch("mcp_server.server._load_app_config", return_value=config),
        patch("mcp_server.server.scrape_all_sites", autospec=True, return_value=RUN_RESULT),
        patch("mcp_server.server._STATUS_PATH", status_path),
        patch("mcp_server.server._get_scraper_logger", return_value=logger),
    ):
        return scrape_jobs(SITES, keywords=KEYWORDS)


def _read_run_done_log_arguments(logger: MagicMock) -> tuple[Any, ...]:
    for logged_call in logger.info.call_args_list:
        if logged_call.args[0].startswith("scrape_jobs done"):
            return logged_call.args[1:]
    raise AssertionError("scrape_jobs done was not logged")


@patch("mcp_server.server.mongo")
def test_saved_per_site_counts_cover_only_pairs_that_succeeded(mock_mongo, tmp_path):
    mock_mongo.insert_run.return_value = "id1"

    _scrape_two_keywords_on_two_sites(tmp_path / "status.json", MagicMock())

    run_metadata = mock_mongo.insert_run.call_args.args[0]["run_metadata"]
    assert run_metadata["per_site_counts"] == {
        "glints": {"devops": 2, "qa": 3},
        "jobstreet": {"qa": 1},
    }
    assert run_metadata["per_site_sources"] == [
        {"site": "glints", "keyword": "devops", "source": "api", "fallback_reason": None},
        {"site": "jobstreet", "keyword": "devops", "source": "html", "fallback_reason": None},
        {"site": "glints", "keyword": "qa", "source": "api", "fallback_reason": None},
        {"site": "jobstreet", "keyword": "qa", "source": "api", "fallback_reason": None},
    ]


@patch("mcp_server.server.mongo")
def test_run_done_log_counts_jobs_of_pairs_that_succeeded(mock_mongo, tmp_path):
    logger = MagicMock()

    _scrape_two_keywords_on_two_sites(tmp_path / "status.json", logger)

    is_ok, error_count, job_count, _duration_seconds = _read_run_done_log_arguments(logger)
    assert (is_ok, error_count, job_count) == (False, 1, 6)


@patch("mcp_server.server.mongo")
def test_status_file_counts_jobs_of_pairs_that_succeeded(mock_mongo, tmp_path):
    status_path = tmp_path / "status.json"

    _scrape_two_keywords_on_two_sites(status_path, MagicMock())

    scrape_status = json.loads(status_path.read_text())
    assert scrape_status["last_run"]["total_jobs"] == 6
    assert scrape_status["last_run"]["error_count"] == 1
    assert scrape_status["per_site"]["glints"]["last_status"] == "ok"
    assert scrape_status["per_site"]["glints"]["last_job_count"] == 3
    assert scrape_status["per_site"]["jobstreet"]["last_status"] == "error"
    assert scrape_status["per_site"]["jobstreet"]["last_job_count"] == 0
    assert scrape_status["per_site"]["jobstreet"]["last_error"] == "fetch failed"
