from __future__ import annotations

from types import MappingProxyType
from typing import Any
from unittest.mock import MagicMock, create_autospec, patch

from scraper.config_loader import AppConfig
from scraper.runner import RunResult

SITE = "glints"
EMPTY_SCRAPE_OUTCOME = RunResult(exit_code=0, results=MappingProxyType({}))


def _make_config() -> MagicMock:
    config = create_autospec(AppConfig, instance=True)
    config.list_enabled_site_names.return_value = (SITE,)
    return config


def _build_keywords(count: int) -> list[str]:
    keywords: list[str] = []
    for index in range(count):
        keywords.append(f"keyword {index}")
    return keywords


def _scrape_and_capture_scrape_all_sites(keywords: list[str]) -> tuple[dict[str, Any], MagicMock]:
    from mcp_server.server import scrape_jobs

    with (
        patch("mcp_server.server._load_app_config", return_value=_make_config()),
        patch("mcp_server.server._write_scrape_status_file"),
        patch(
            "mcp_server.server.scrape_all_sites", autospec=True, return_value=EMPTY_SCRAPE_OUTCOME
        ) as scrape_all_sites,
    ):
        scrape_response = scrape_jobs(keywords=keywords, sites=[SITE], save_run=False)
    return scrape_response, scrape_all_sites


def test_scrape_jobs_refuses_more_than_ten_keywords_without_scraping():
    scrape_response, scrape_all_sites = _scrape_and_capture_scrape_all_sites(_build_keywords(12))

    assert scrape_response == {
        "ok": False,
        "keywords": [],
        "requested_sites": [SITE],
        "exit_code": 1,
        "results": [],
        "errors": [
            {"keyword": None, "site": None, "reason": "keywords must be 10 or fewer, got 12"}
        ],
        "mongo_id": None,
    }
    scrape_all_sites.assert_not_called()


def test_scrape_jobs_accepts_exactly_ten_keywords():
    ten_keywords = _build_keywords(10)

    _, scrape_all_sites = _scrape_and_capture_scrape_all_sites(ten_keywords)

    assert scrape_all_sites.call_args.kwargs["keywords"] == ten_keywords


def test_scrape_jobs_counts_keywords_after_dropping_blank_ones():
    ten_keywords = _build_keywords(10)

    _, scrape_all_sites = _scrape_and_capture_scrape_all_sites([*ten_keywords, "", "   "])

    assert scrape_all_sites.call_args.kwargs["keywords"] == ten_keywords
