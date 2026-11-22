from __future__ import annotations

import json
from unittest.mock import MagicMock

from scraper.api.client import ApiError
from scraper.api.location_search_plan import LocationSearchPlan, build_location_search_plan
from scraper.api.registry import API_SOURCES
from scraper.api.upwork import UpworkApi
from scraper.config_loader import ApiConfig
from scraper.runner import FilteredAndRawPayloads, _is_api_usable_for_site, scrape_site_for_keyword
from scraper.sites import SCRAPERS
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


ENABLED_API = ApiConfig(enabled=True)
PLAN_WITHOUT_ANY_REQUEST = LocationSearchPlan(city_values=(), is_country_wide=False)
PLAN_WITH_ONE_CITY = LocationSearchPlan(city_values=("Jakarta Raya",), is_country_wide=False)
COUNTRY_WIDE_ONLY_PLAN = LocationSearchPlan(city_values=(), is_country_wide=True)


def test_api_only_site_always_has_one_request_whatever_its_filter():
    upwork_plan = build_location_search_plan("upwork", [])

    assert upwork_plan == COUNTRY_WIDE_ONLY_PLAN
    assert _is_api_usable_for_site(ENABLED_API, "upwork", upwork_plan) is True


def test_api_only_site_with_a_plan_without_any_request_cannot_call_the_api():
    assert _is_api_usable_for_site(ENABLED_API, "upwork", PLAN_WITHOUT_ANY_REQUEST) is False


def test_html_site_with_a_plan_without_any_request_uses_the_html_path():
    assert _is_api_usable_for_site(ENABLED_API, "glints", PLAN_WITHOUT_ANY_REQUEST) is False


def test_html_site_with_a_city_or_country_request_uses_the_api_path():
    assert _is_api_usable_for_site(ENABLED_API, "glints", PLAN_WITH_ONE_CITY) is True
    assert _is_api_usable_for_site(ENABLED_API, "glints", COUNTRY_WIDE_ONLY_PLAN) is True


def test_disabled_api_or_site_without_an_api_source_is_not_usable():
    disabled_api = ApiConfig(enabled=False)

    assert _is_api_usable_for_site(disabled_api, "glints", PLAN_WITH_ONE_CITY) is False
    assert _is_api_usable_for_site(ENABLED_API, "indeed", PLAN_WITH_ONE_CITY) is False
