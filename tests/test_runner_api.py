from __future__ import annotations

import json
from unittest.mock import MagicMock

from scraper.api.client import ApiError
from scraper.runner import run_one
from scraper.sites.linkedin import LinkedinScraper
from scraper.types import empty_job

FIELDS = frozenset(
    {"site", "matched_keyword", "title", "company", "url", "location", "requirements"}
)


def _fetcher(html: str | None):
    fetcher = MagicMock()
    result = MagicMock()
    result.html = html
    result.attempts = ()
    fetcher.fetch.return_value = result
    return fetcher


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


def test_api_success_skips_html_fetch_and_records_source():
    fetcher = _fetcher(HTML_CARD)
    result = run_one(
        _scraper(),
        fetcher,
        "devops",
        FIELDS - {"requirements"},
        None,
        {},
        api_search=lambda: [_api_job("1"), _api_job("2")],
    )
    out, raw = result.filtered, result.raw
    assert out["count"] == 2
    assert out["source"] == "api"
    assert out["fallback_reason"] is None
    assert raw["source"] == "api"
    fetcher.fetch.assert_not_called()


def test_api_error_falls_back_to_html():
    def broken():
        raise ApiError("http_429", "slow down")

    result = run_one(
        _scraper(),
        _fetcher(HTML_CARD),
        "devops",
        FIELDS - {"requirements"},
        None,
        {},
        api_search=broken,
    )
    out = result.filtered
    assert out["source"] == "html"
    assert out["fallback_reason"] == "http_429"  # code only, no response body
    for payload in (result.filtered, result.raw):
        assert "slow down" not in json.dumps(payload)
    assert [j["title"] for j in out["jobs"]] == ["Html Role"]


def test_zero_api_results_is_not_a_fallback():
    fetcher = _fetcher(HTML_CARD)
    result = run_one(
        _scraper(),
        fetcher,
        "devops",
        FIELDS - {"requirements"},
        None,
        {},
        api_search=lambda: [],
    )
    out = result.filtered
    assert out["count"] == 0
    assert out["source"] == "api"
    fetcher.fetch.assert_not_called()


def test_without_api_search_source_is_html():
    result = run_one(_scraper(), _fetcher(HTML_CARD), "devops", FIELDS - {"requirements"}, None, {})
    assert result.filtered["source"] == "html"


def test_detail_api_used_then_page_fallback_per_job():
    fetcher = _fetcher("<div class='show-more-less-html__markup'>From page</div>")

    def detail(job):
        if job["job_id"] == "1":
            return "From api"
        raise ApiError("http_500")

    result = run_one(
        _scraper(),
        fetcher,
        "devops",
        FIELDS,
        None,
        {},
        api_search=lambda: [_api_job("1"), _api_job("2")],
        api_detail=detail,
    )
    jobs = {j["title"]: j["requirements"] for j in result.filtered["jobs"]}
    assert jobs["Role 1"] == "From api"
    assert jobs["Role 2"] is not None and "From page" in jobs["Role 2"]


def test_unexpected_api_exception_also_falls_back():
    def crashing():
        raise KeyError("jobsInPage")

    result = run_one(
        _scraper(),
        _fetcher(HTML_CARD),
        "devops",
        FIELDS - {"requirements"},
        None,
        {},
        api_search=crashing,
    )
    out = result.filtered
    assert out["source"] == "html"
    assert out["fallback_reason"] == "unexpected_error:KeyError"
    assert [j["title"] for j in out["jobs"]] == ["Html Role"]
