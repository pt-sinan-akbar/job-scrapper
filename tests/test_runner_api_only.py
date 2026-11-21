from __future__ import annotations

import json
from unittest.mock import MagicMock

from scraper.api.client import ApiError
from scraper.api.registry import API_SOURCES
from scraper.api.upwork import UpworkApi
from scraper.config_loader import ApiConfig
from scraper.runner import FilteredAndRawPayloads, _is_api_usable_for_site, scrape_site_for_keyword
from scraper.sites import SCRAPERS
from scraper.sites.glints import GlintsScraper
from scraper.sites.upwork import UpworkScraper
from scraper.types import Job, empty_job
from tests.runner_fakes import build_html_downloader_returning

FIELDS = frozenset({"site", "matched_keyword", "title", "company", "url", "requirements"})
URL = "https://www.upwork.com/nx/search/jobs/?q=python"


def _scraper() -> UpworkScraper:
    return UpworkScraper(url=URL, limit=30)


def _run(
    html_downloader: MagicMock, search_jobs_via_api, read_requirements_via_api=None
) -> FilteredAndRawPayloads:
    return scrape_site_for_keyword(
        _scraper(),
        html_downloader,
        "python",
        FIELDS,
        None,
        {},
        search_jobs_via_api=search_jobs_via_api,
        read_requirements_via_api=read_requirements_via_api,
    )


def _job() -> Job:
    job = empty_job("upwork", "Role", "Upwork Client")
    job["url"] = "https://www.upwork.com/jobs/~1"
    return job


def test_upwork_is_registered():
    assert SCRAPERS["upwork"] is UpworkScraper
    assert API_SOURCES["upwork"] is UpworkApi


def test_scraper_is_api_only_and_parses_nothing():
    assert _scraper().api_only is True
    assert _scraper().parse("<html></html>") == []


def test_api_error_returns_an_error_and_never_downloads_html():
    html_downloader = build_html_downloader_returning(None)

    def _fail():
        raise ApiError("http_403", "blocked")

    result = _run(html_downloader, _fail)

    payload = result.filtered
    assert payload["error"] == "api failed: http_403"
    assert payload["source"] == "api"
    assert "blocked" not in json.dumps(payload)
    raw = result.raw
    assert raw["count"] == 0
    html_downloader.download_html.assert_not_called()


def test_unexpected_exception_returns_an_error_and_never_downloads_html():
    html_downloader = build_html_downloader_returning(None)

    def _crash():
        raise KeyError("shape")

    result = _run(html_downloader, _crash)

    payload = result.filtered
    assert payload["error"] == "api failed: unexpected_error:KeyError"
    html_downloader.download_html.assert_not_called()


def test_missing_api_search_returns_an_error_and_never_downloads_html():
    html_downloader = build_html_downloader_returning(None)

    result = _run(html_downloader, None)

    payload = result.filtered
    assert payload["error"] == "api failed: api_disabled"
    html_downloader.download_html.assert_not_called()


def test_blank_requirements_never_download_the_job_page():
    html_downloader = build_html_downloader_returning(None)

    result = _run(html_downloader, lambda: [_job()], lambda _job: None)

    payload = result.filtered
    assert payload["count"] == 1
    html_downloader.download_html.assert_not_called()


def test_zero_results_is_not_an_error():
    result = _run(build_html_downloader_returning(None), lambda: [])

    payload = result.filtered
    assert "error" not in payload
    assert payload["count"] == 0


def test_api_only_site_without_locations_cannot_call_the_api():
    empty = ApiConfig(enabled=True, locations=(), country_wide=False)
    remote = ApiConfig(enabled=True, locations=("Remote",), country_wide=False)

    assert _is_api_usable_for_site(_scraper(), empty, "upwork") is False
    assert _is_api_usable_for_site(_scraper(), remote, "upwork") is True


def test_html_site_without_locations_still_uses_the_api_path():
    scraper = GlintsScraper(url="https://glints.com/id/opportunities/jobs/explore", limit=30)
    empty = ApiConfig(enabled=True, locations=(), country_wide=False)

    assert _is_api_usable_for_site(scraper, empty, "glints") is True
