from __future__ import annotations

import sys
from typing import Any

import pytest
from curl_cffi import requests as cffi_requests

from scraper.api.client import ApiError
from scraper.api.location_search_plan import LocationSearchPlan
from scraper.runner import scrape_site_for_keyword
from scraper.sites.indeed import IndeedScraper
from tests.log_lines import list_log_lines_containing, list_warning_or_above_log_lines
from tests.runner_fakes import build_html_downloader_returning

INDEED_URL = "https://id.indeed.com/jobs?q=python&l=Indonesia&fromage=1"
FIELDS = frozenset({"site", "matched_keyword", "title", "company", "url", "location"})
SEARCH_PAGE_HTML = "<html>ok</html>"
BLOCKED_RESPONSE_BODY = "blocked-response-body"
PROXY_PASSWORD = "proxy-password-9431"
GRAPHQL_ERROR_MESSAGE = "graphql-error-message-5512"
ONE_JOB_BODY = {
    "data": {
        "jobSearch": {
            "results": [
                {"job": {"title": "Python Dev", "employer": {"name": "Acme"}, "key": "abc"}}
            ]
        }
    }
}
ZERO_JOBS_BODY: dict[str, Any] = {"data": {"jobSearch": {"results": []}}}
ONE_JOB_BODY_WITH_GRAPHQL_ERRORS = {
    "errors": [{"message": GRAPHQL_ERROR_MESSAGE}],
    "data": ONE_JOB_BODY["data"],
}


class _FakeIndeedResponse:
    def __init__(self, status_code: int, body: Any) -> None:
        self.status_code = status_code
        self._body = body
        self.text = str(body)

    def json(self) -> Any:
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


def _answer_indeed_with(monkeypatch: pytest.MonkeyPatch, response_or_error: Any) -> None:
    def fake_post(*args: Any, **kwargs: Any) -> Any:
        if isinstance(response_or_error, Exception):
            raise response_or_error
        return response_or_error

    monkeypatch.setattr(cffi_requests, "post", fake_post)


def _indeed_scraper() -> IndeedScraper:
    return IndeedScraper(url=INDEED_URL, limit=5)


def test_indeed_returns_the_jobs_of_a_good_response(monkeypatch: pytest.MonkeyPatch):
    _answer_indeed_with(monkeypatch, _FakeIndeedResponse(200, ONE_JOB_BODY))

    jobs = _indeed_scraper().parse("")

    assert [(job["title"], job["company"], job["url"]) for job in jobs] == [
        ("Python Dev", "Acme", "https://id.indeed.com/viewjob?jk=abc")
    ]


@pytest.mark.parametrize(
    ("response_or_error", "expected_code"),
    [
        (_FakeIndeedResponse(403, "blocked"), "http_403"),
        (ConnectionError("no route"), "runtime_error"),
        (_FakeIndeedResponse(200, ValueError("not json")), "non_json"),
        (
            _FakeIndeedResponse(200, {"errors": [{"message": "bad query"}], "data": None}),
            "graphql_error",
        ),
    ],
)
def test_indeed_failure_raises_an_api_error_with_a_short_code(
    monkeypatch: pytest.MonkeyPatch, response_or_error: Any, expected_code: str
):
    _answer_indeed_with(monkeypatch, response_or_error)

    with pytest.raises(ApiError) as raised:
        _indeed_scraper().parse("")

    assert raised.value.code == expected_code


def test_indeed_failure_is_reported_as_an_error_not_as_zero_jobs(
    monkeypatch: pytest.MonkeyPatch,
):
    _answer_indeed_with(monkeypatch, _FakeIndeedResponse(403, "blocked"))

    result = scrape_site_for_keyword(
        _indeed_scraper(),
        build_html_downloader_returning(None),
        "python",
        FIELDS,
        None,
        {},
    )

    assert result.filtered["error"] == "api failed: http_403"
    assert "jobs" not in result.filtered
    assert "blocked" not in str(result.filtered)


def test_indeed_missing_curl_cffi_raises_a_not_installed_api_error(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setitem(sys.modules, "curl_cffi", None)

    with pytest.raises(ApiError) as raised:
        _indeed_scraper().parse("")

    assert raised.value.code == "not_installed"


def test_indeed_response_with_graphql_errors_and_results_returns_the_jobs(
    monkeypatch: pytest.MonkeyPatch,
):
    _answer_indeed_with(monkeypatch, _FakeIndeedResponse(200, ONE_JOB_BODY_WITH_GRAPHQL_ERRORS))

    jobs = _indeed_scraper().parse("")

    job_titles: list[Any] = []
    for job in jobs:
        job_titles.append(job["title"])
    assert job_titles == ["Python Dev"]


def test_indeed_search_never_downloads_the_search_page(monkeypatch: pytest.MonkeyPatch):
    _answer_indeed_with(monkeypatch, _FakeIndeedResponse(200, ONE_JOB_BODY))
    html_downloader = build_html_downloader_returning(SEARCH_PAGE_HTML)

    payloads = scrape_site_for_keyword(
        _indeed_scraper(), html_downloader, "python", FIELDS, None, {}
    )

    assert payloads.filtered["count"] == 1
    html_downloader.download_html.assert_not_called()


@pytest.mark.parametrize(
    ("response_or_error", "expected_error", "failure_detail"),
    [
        (
            _FakeIndeedResponse(403, BLOCKED_RESPONSE_BODY),
            "api failed: http_403",
            BLOCKED_RESPONSE_BODY,
        ),
        (
            ConnectionError(f"proxy http://user:{PROXY_PASSWORD}@proxy.test:8080 refused"),
            "api failed: runtime_error",
            PROXY_PASSWORD,
        ),
        (
            _FakeIndeedResponse(200, {"errors": [{"message": GRAPHQL_ERROR_MESSAGE}]}),
            "api failed: graphql_error",
            GRAPHQL_ERROR_MESSAGE,
        ),
    ],
)
def test_indeed_failure_is_reported_without_downloading_the_search_page_or_leaking_detail(
    monkeypatch: pytest.MonkeyPatch,
    scraper_log_records: pytest.LogCaptureFixture,
    response_or_error: Any,
    expected_error: str,
    failure_detail: str,
):
    _answer_indeed_with(monkeypatch, response_or_error)
    html_downloader = build_html_downloader_returning(SEARCH_PAGE_HTML)

    payloads = scrape_site_for_keyword(
        _indeed_scraper(), html_downloader, "python", FIELDS, None, {}
    )

    assert payloads.filtered["error"] == expected_error
    assert payloads.raw["error"] == expected_error
    html_downloader.download_html.assert_not_called()
    assert failure_detail not in str(payloads.filtered)
    assert failure_detail not in str(payloads.raw)
    warning_or_above_log_lines = list_warning_or_above_log_lines(scraper_log_records)
    assert list_log_lines_containing(warning_or_above_log_lines, failure_detail) == []


def test_indeed_search_with_no_jobs_logs_no_page_layout_warning(
    monkeypatch: pytest.MonkeyPatch, scraper_log_records: pytest.LogCaptureFixture
):
    _answer_indeed_with(monkeypatch, _FakeIndeedResponse(200, ZERO_JOBS_BODY))

    payloads = scrape_site_for_keyword(
        _indeed_scraper(),
        build_html_downloader_returning(SEARCH_PAGE_HTML),
        "python",
        FIELDS,
        None,
        {},
    )

    assert payloads.filtered["count"] == 0
    assert list_log_lines_containing(scraper_log_records.messages, "page layout") == []


class _RecordingIndeedApi:
    def __init__(self, response_or_error_by_search_location: dict[str, Any]) -> None:
        self._response_or_error_by_search_location = response_or_error_by_search_location
        self.graphql_queries: list[str] = []

    def post(self, *args: Any, **kwargs: Any) -> Any:
        graphql_query = kwargs["json"]["query"]
        self.graphql_queries.append(graphql_query)
        response_or_error = self._find_response_or_error_for_query(graphql_query)
        if isinstance(response_or_error, Exception):
            raise response_or_error
        return response_or_error

    def list_searched_locations(self) -> list[str]:
        searched_locations: list[str] = []
        for graphql_query in self.graphql_queries:
            text_after_where = graphql_query.split('where: "', 1)[1]
            searched_locations.append(text_after_where.split('"', 1)[0])
        return searched_locations

    def _find_response_or_error_for_query(self, graphql_query: str) -> Any:
        for (
            search_location,
            response_or_error,
        ) in self._response_or_error_by_search_location.items():
            if f'where: "{search_location}"' in graphql_query:
                return response_or_error
        raise AssertionError(f"unexpected indeed query: {graphql_query}")


def _build_response_with_job_keys(*job_keys: str) -> _FakeIndeedResponse:
    search_results: list[dict[str, Any]] = []
    for job_key in job_keys:
        search_results.append(
            {"job": {"title": f"Role {job_key}", "employer": {"name": "Acme"}, "key": job_key}}
        )
    return _FakeIndeedResponse(200, {"data": {"jobSearch": {"results": search_results}}})


def _record_indeed_requests(
    monkeypatch: pytest.MonkeyPatch, response_or_error_by_search_location: dict[str, Any]
) -> _RecordingIndeedApi:
    recording_indeed_api = _RecordingIndeedApi(response_or_error_by_search_location)
    monkeypatch.setattr(cffi_requests, "post", recording_indeed_api.post)
    return recording_indeed_api


def _indeed_scraper_with_plan(
    location_search_plan: LocationSearchPlan | None, limit: int = 5
) -> IndeedScraper:
    return IndeedScraper(url=INDEED_URL, limit=limit, location_search_plan=location_search_plan)


def _list_job_ids(jobs: list[Any]) -> list[Any]:
    job_ids: list[Any] = []
    for job in jobs:
        job_ids.append(job["job_id"])
    return job_ids


def test_indeed_sends_one_request_per_city_value_then_one_for_the_country(
    monkeypatch: pytest.MonkeyPatch,
):
    recording_indeed_api = _record_indeed_requests(
        monkeypatch,
        {
            "Jakarta": _build_response_with_job_keys("j1"),
            "Bandung": _build_response_with_job_keys("b1"),
            "Indonesia": _build_response_with_job_keys("i1"),
        },
    )
    plan = LocationSearchPlan(city_values=("Jakarta", "Bandung"), is_country_wide=True)

    jobs = _indeed_scraper_with_plan(plan).parse("")

    assert recording_indeed_api.list_searched_locations() == ["Jakarta", "Bandung", "Indonesia"]
    assert _list_job_ids(jobs) == ["j1", "b1", "i1"]


def test_indeed_sends_no_country_request_when_only_cities_are_picked(
    monkeypatch: pytest.MonkeyPatch,
):
    recording_indeed_api = _record_indeed_requests(
        monkeypatch, {"Bekasi": _build_response_with_job_keys("k1")}
    )
    plan = LocationSearchPlan(city_values=("Bekasi",), is_country_wide=False)

    jobs = _indeed_scraper_with_plan(plan).parse("")

    assert recording_indeed_api.list_searched_locations() == ["Bekasi"]
    assert _list_job_ids(jobs) == ["k1"]


def test_indeed_sends_only_the_country_request_for_a_country_wide_only_plan(
    monkeypatch: pytest.MonkeyPatch,
):
    recording_indeed_api = _record_indeed_requests(
        monkeypatch, {"Indonesia": _build_response_with_job_keys("i1")}
    )
    plan = LocationSearchPlan(city_values=(), is_country_wide=True)

    _indeed_scraper_with_plan(plan).parse("")

    assert recording_indeed_api.list_searched_locations() == ["Indonesia"]


def test_indeed_interleaves_the_cities_and_drops_repeated_jobs(
    monkeypatch: pytest.MonkeyPatch,
):
    _record_indeed_requests(
        monkeypatch,
        {
            "Jakarta": _build_response_with_job_keys("j1", "j2", "j3"),
            "Bandung": _build_response_with_job_keys("b1"),
            "Indonesia": _build_response_with_job_keys("i1", "j1"),
        },
    )
    plan = LocationSearchPlan(city_values=("Jakarta", "Bandung"), is_country_wide=True)

    jobs = _indeed_scraper_with_plan(plan).parse("")

    assert _list_job_ids(jobs) == ["j1", "b1", "i1", "j2", "j3"]


def test_indeed_keeps_the_jobs_of_every_city_past_the_site_limit(
    monkeypatch: pytest.MonkeyPatch,
):
    _record_indeed_requests(
        monkeypatch,
        {
            "Jakarta": _build_response_with_job_keys("j1"),
            "Bandung": _build_response_with_job_keys("b1"),
        },
    )
    plan = LocationSearchPlan(city_values=("Jakarta", "Bandung"), is_country_wide=False)

    jobs = _indeed_scraper_with_plan(plan, limit=1).parse("")

    assert _list_job_ids(jobs) == ["j1", "b1"]


def test_indeed_searches_within_five_miles_of_each_location(monkeypatch: pytest.MonkeyPatch):
    recording_indeed_api = _record_indeed_requests(
        monkeypatch, {"Jakarta": _build_response_with_job_keys("j1")}
    )
    plan = LocationSearchPlan(city_values=("Jakarta",), is_country_wide=False)

    _indeed_scraper_with_plan(plan).parse("")

    assert "radius: 5, radiusUnit: MILES" in recording_indeed_api.graphql_queries[0]


@pytest.mark.parametrize(
    "location_search_plan",
    [None, LocationSearchPlan(city_values=(), is_country_wide=False)],
)
def test_indeed_without_a_plan_request_searches_the_location_of_the_url(
    monkeypatch: pytest.MonkeyPatch, location_search_plan: LocationSearchPlan | None
):
    recording_indeed_api = _record_indeed_requests(
        monkeypatch, {"Surabaya": _build_response_with_job_keys("s1")}
    )
    scraper = IndeedScraper(
        url="https://id.indeed.com/jobs?q=python&l=Surabaya",
        limit=5,
        location_search_plan=location_search_plan,
    )

    jobs = scraper.parse("")

    assert recording_indeed_api.list_searched_locations() == ["Surabaya"]
    assert _list_job_ids(jobs) == ["s1"]


def test_indeed_error_in_a_later_city_request_still_raises_the_api_error(
    monkeypatch: pytest.MonkeyPatch,
):
    _record_indeed_requests(
        monkeypatch,
        {
            "Jakarta": _build_response_with_job_keys("j1"),
            "Bandung": _FakeIndeedResponse(403, "blocked"),
        },
    )
    plan = LocationSearchPlan(city_values=("Jakarta", "Bandung"), is_country_wide=True)

    with pytest.raises(ApiError) as raised:
        _indeed_scraper_with_plan(plan).parse("")

    assert raised.value.code == "http_403"
