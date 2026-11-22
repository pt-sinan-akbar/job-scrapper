from __future__ import annotations

from types import MappingProxyType
from typing import Any
from unittest.mock import MagicMock, create_autospec, patch

from scraper.config_loader import AppConfig
from scraper.runner import RunResult

KEYWORD = "data analyst"
SITE = "glints"
EMPTY_SCRAPE_OUTCOME = RunResult(exit_code=0, results=MappingProxyType({}))


def _make_config() -> MagicMock:
    config = create_autospec(AppConfig, instance=True)
    config.list_enabled_site_names.return_value = (SITE,)
    return config


def _scrape_and_capture_runner(**kwargs: Any) -> tuple[dict[str, Any], MagicMock]:
    from mcp_server.server import scrape_jobs

    with (
        patch("mcp_server.server._load_app_config", return_value=_make_config()),
        patch(
            "mcp_server.server.scrape_all_sites", autospec=True, return_value=EMPTY_SCRAPE_OUTCOME
        ) as scrape_all_sites,
    ):
        scrape_response = scrape_jobs(keywords=[KEYWORD], sites=[SITE], save_run=False, **kwargs)
    return scrape_response, scrape_all_sites


def test_scrape_jobs_passes_the_requested_max_age_to_the_runner():
    _, scrape_all_sites = _scrape_and_capture_runner(max_age_hours=168)

    assert scrape_all_sites.call_args.kwargs["requested_max_age_hours"] == 168


def test_scrape_jobs_without_max_age_passes_none_to_the_runner():
    _, scrape_all_sites = _scrape_and_capture_runner()

    assert scrape_all_sites.call_args.kwargs["requested_max_age_hours"] is None


def test_scrape_jobs_refuses_an_unlisted_max_age_without_scraping():
    scrape_response, scrape_all_sites = _scrape_and_capture_runner(max_age_hours=48)

    assert scrape_response["ok"] is False
    assert scrape_response["exit_code"] == 1
    assert scrape_response["keywords"] == []
    assert scrape_response["results"] == []
    assert scrape_response["mongo_id"] is None
    assert scrape_response["errors"] == [
        {
            "keyword": None,
            "site": None,
            "reason": "unknown max_age_hours: 48. allowed: 72, 168, 720",
        }
    ]
    scrape_all_sites.assert_not_called()
