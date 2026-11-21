from __future__ import annotations

import json

import pytest

from scraper.api.client import ApiError
from scraper.runner import scrape_site_for_keyword
from scraper.sites.linkedin import LinkedinScraper
from scraper.types import empty_job
from tests.log_lines import list_log_lines_containing, list_warning_or_above_log_lines
from tests.runner_fakes import build_html_downloader_returning

FIELDS = frozenset(
    {"site", "matched_keyword", "title", "company", "url", "location", "requirements"}
)
JOB_PAGE_HTML = "<div class='show-more-less-html__markup'>From page</div>"
REQUIREMENTS_FAILURE_DETAIL = "body via http://user:proxy-password-7719@proxy.test:8080"


def _api_job(job_id: str):
    job = empty_job("linkedin", f"Role {job_id}", "Acme")
    job["job_id"] = job_id
    job["url"] = f"https://www.linkedin.com/jobs/view/{job_id}"
    job["location"] = "Jakarta"
    return job


HTML_CARD = (
    "<li><h3 class='base-search-card__title'>Html Role</h3>"
    "<h4 class='base-search-card__subtitle'><a>Acme</a></h4>"
    "<span class='job-search-card__location'>Jakarta</span>"
    "<a class='base-card__full-link' href='https://www.linkedin.com/jobs/view/777'></a></li>"
)


def _scraper():
    return LinkedinScraper(url="https://www.linkedin.com/jobs-guest/x", limit=10)


def test_api_success_skips_html_download_and_records_source():
    html_downloader = build_html_downloader_returning(HTML_CARD)
    result = scrape_site_for_keyword(
        _scraper(),
        html_downloader,
        "devops",
        FIELDS - {"requirements"},
        None,
        {},
        search_jobs_via_api=lambda: [_api_job("1"), _api_job("2")],
    )
    out, raw = result.filtered, result.raw
    assert out["count"] == 2
    assert out["source"] == "api"
    assert out["fallback_reason"] is None
    assert raw["source"] == "api"
    html_downloader.download_html.assert_not_called()


def test_api_error_falls_back_to_html():
    def broken():
        raise ApiError("http_429", "slow down")

    result = scrape_site_for_keyword(
        _scraper(),
        build_html_downloader_returning(HTML_CARD),
        "devops",
        FIELDS - {"requirements"},
        None,
        {},
        search_jobs_via_api=broken,
    )
    out = result.filtered
    assert out["source"] == "html"
    assert out["fallback_reason"] == "http_429"  # code only, no response body
    for payload in (result.filtered, result.raw):
        assert "slow down" not in json.dumps(payload)
    assert [j["title"] for j in out["jobs"]] == ["Html Role"]


def test_zero_api_results_is_not_a_fallback():
    html_downloader = build_html_downloader_returning(HTML_CARD)
    result = scrape_site_for_keyword(
        _scraper(),
        html_downloader,
        "devops",
        FIELDS - {"requirements"},
        None,
        {},
        search_jobs_via_api=lambda: [],
    )
    out = result.filtered
    assert out["count"] == 0
    assert out["source"] == "api"
    html_downloader.download_html.assert_not_called()


def test_without_api_search_source_is_html():
    result = scrape_site_for_keyword(
        _scraper(),
        build_html_downloader_returning(HTML_CARD),
        "devops",
        FIELDS - {"requirements"},
        None,
        {},
    )
    assert result.filtered["source"] == "html"


def test_detail_api_used_then_page_fallback_per_job():
    html_downloader = build_html_downloader_returning(
        "<div class='show-more-less-html__markup'>From page</div>"
    )

    def detail(job):
        if job["job_id"] == "1":
            return "From api"
        raise ApiError("http_500")

    result = scrape_site_for_keyword(
        _scraper(),
        html_downloader,
        "devops",
        FIELDS,
        None,
        {},
        search_jobs_via_api=lambda: [_api_job("1"), _api_job("2")],
        read_requirements_via_api=detail,
    )
    jobs = {j["title"]: j["requirements"] for j in result.filtered["jobs"]}
    assert jobs["Role 1"] == "From api"
    assert jobs["Role 2"] is not None and "From page" in jobs["Role 2"]


def test_unexpected_api_exception_also_falls_back():
    def crashing():
        raise KeyError("jobsInPage")

    result = scrape_site_for_keyword(
        _scraper(),
        build_html_downloader_returning(HTML_CARD),
        "devops",
        FIELDS - {"requirements"},
        None,
        {},
        search_jobs_via_api=crashing,
    )
    out = result.filtered
    assert out["source"] == "html"
    assert out["fallback_reason"] == "unexpected_error:KeyError"
    assert [j["title"] for j in out["jobs"]] == ["Html Role"]


def _build_api_job_with_location(job_id: str, location: str, employment_type: str | None = None):
    job = _api_job(job_id)
    job["location"] = location
    job["employment_type"] = employment_type
    return job


def test_api_job_outside_the_location_filter_is_dropped_and_a_matching_one_is_kept():
    payloads = scrape_site_for_keyword(
        _scraper(),
        build_html_downloader_returning(HTML_CARD),
        "devops",
        FIELDS - {"requirements"},
        None,
        {"location": ["jakarta"]},
        search_jobs_via_api=lambda: [
            _build_api_job_with_location("1", "Jakarta"),
            _build_api_job_with_location("2", "Bandung"),
        ],
    )

    kept_job_titles: list[str] = []
    for job in payloads.filtered["jobs"]:
        kept_job_titles.append(job["title"])
    assert kept_job_titles == ["Role 1"]
    assert payloads.filtered["source"] == "api"
    assert payloads.raw["count"] == 2


def test_api_payload_reports_the_full_filter_including_location():
    payloads = scrape_site_for_keyword(
        _scraper(),
        build_html_downloader_returning(HTML_CARD),
        "devops",
        FIELDS - {"requirements"},
        None,
        {"location": ["jakarta"], "employment_type": ["full"]},
        search_jobs_via_api=lambda: [
            _build_api_job_with_location("1", "Jakarta", "full_time"),
            _build_api_job_with_location("2", "Jakarta", "contract"),
            _build_api_job_with_location("3", "Bandung", "full_time"),
        ],
    )

    kept_job_titles: list[str] = []
    for job in payloads.filtered["jobs"]:
        kept_job_titles.append(job["title"])
    assert kept_job_titles == ["Role 1"]
    assert payloads.filtered["source"] == "api"
    assert payloads.filtered["filter"] == {"location": ["jakarta"], "employment_type": ["full"]}


def test_html_jobs_are_still_filtered_by_location():
    def raise_rate_limited_api_error():
        raise ApiError("http_429", "slow down")

    result = scrape_site_for_keyword(
        _scraper(),
        build_html_downloader_returning(HTML_CARD),
        "devops",
        FIELDS - {"requirements"},
        None,
        {"location": ["bandung"]},
        search_jobs_via_api=raise_rate_limited_api_error,
    )
    out = result.filtered
    assert out["source"] == "html"
    assert out["jobs"] == []
    assert out["filter"] == {"location": ["bandung"]}


def test_html_source_with_no_jobs_logs_a_warning(scraper_log_records: pytest.LogCaptureFixture):
    result = scrape_site_for_keyword(
        _scraper(),
        build_html_downloader_returning("<html><body>nothing here</body></html>"),
        "devops",
        FIELDS - {"requirements"},
        None,
        {},
    )

    assert result.filtered["count"] == 0
    assert (
        "[linkedin:devops] html source returned 0 jobs; the page layout may have changed"
        in scraper_log_records.messages
    )


def test_api_source_with_no_jobs_logs_no_layout_warning(
    scraper_log_records: pytest.LogCaptureFixture,
):
    scrape_site_for_keyword(
        _scraper(),
        build_html_downloader_returning(HTML_CARD),
        "devops",
        FIELDS - {"requirements"},
        None,
        {},
        search_jobs_via_api=lambda: [],
    )

    assert list_log_lines_containing(scraper_log_records.messages, "page layout") == []


def test_failed_requirements_api_call_logs_a_warning(
    scraper_log_records: pytest.LogCaptureFixture,
):
    def raise_requirements_api_error(job):
        raise ApiError("http_500", REQUIREMENTS_FAILURE_DETAIL)

    scrape_site_for_keyword(
        _scraper(),
        build_html_downloader_returning(JOB_PAGE_HTML),
        "devops",
        FIELDS,
        None,
        {},
        search_jobs_via_api=lambda: [_api_job("1")],
        read_requirements_via_api=raise_requirements_api_error,
    )

    assert (
        "[linkedin] requirements api failed for "
        "https://www.linkedin.com/jobs/view/1 (http_500)" in scraper_log_records.messages
    )
    warning_or_above_log_lines = list_warning_or_above_log_lines(scraper_log_records)
    assert list_log_lines_containing(warning_or_above_log_lines, REQUIREMENTS_FAILURE_DETAIL) == []


def test_crashed_requirements_api_call_logs_only_the_exception_type_as_a_warning(
    scraper_log_records: pytest.LogCaptureFixture,
):
    def raise_unexpected_requirements_error(job):
        raise RuntimeError(REQUIREMENTS_FAILURE_DETAIL)

    scrape_site_for_keyword(
        _scraper(),
        build_html_downloader_returning(JOB_PAGE_HTML),
        "devops",
        FIELDS,
        None,
        {},
        search_jobs_via_api=lambda: [_api_job("1")],
        read_requirements_via_api=raise_unexpected_requirements_error,
    )

    assert (
        "[linkedin] requirements api failed for "
        "https://www.linkedin.com/jobs/view/1 (RuntimeError)" in scraper_log_records.messages
    )
    warning_or_above_log_lines = list_warning_or_above_log_lines(scraper_log_records)
    assert list_log_lines_containing(warning_or_above_log_lines, REQUIREMENTS_FAILURE_DETAIL) == []
