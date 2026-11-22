from __future__ import annotations

import pytest

from scraper.api.client import ApiError
from scraper.api.location_search_plan import LocationSearchPlan
from scraper.api.source import (
    dedup_jobs,
    interleave_job_streams_round_robin,
    search_all,
)
from scraper.types import Job, empty_job


def _job(job_id: str | None, location: str, url: str | None = None) -> Job:
    job = empty_job("jobstreet", f"T{job_id}", "C")
    job["job_id"] = job_id
    job["url"] = url
    job["location"] = location
    return job


class StubSource:
    name = "stub"
    country_location: str | None = "COUNTRY"

    def __init__(self, by_location: dict[str | None, list[Job] | Exception]) -> None:
        self.by_location = by_location
        self.calls: list[tuple[str, str | None, int | None, int]] = []

    def search(self, keyword: str, location: str | None, max_age_hours: int | None, limit: int):
        self.calls.append((keyword, location, max_age_hours, limit))
        result = self.by_location[location]
        if isinstance(result, Exception):
            raise result
        return list(result)

    def detail(self, job: Job) -> str | None:
        return None


def _plan(*city_values: str, is_country_wide: bool = False) -> LocationSearchPlan:
    return LocationSearchPlan(city_values=city_values, is_country_wide=is_country_wide)


def test_one_call_per_city_then_dedup():
    source = StubSource(
        {"A": [_job("1", "Jakarta"), _job("2", "Jakarta")], "B": [_job("2", "Jakarta")]}
    )
    jobs = search_all(source, "devops", _plan("A", "B"), max_age_hours=72, limit=30)
    assert [j["job_id"] for j in jobs] == ["1", "2"]
    assert source.calls == [("devops", "A", 72, 30), ("devops", "B", 72, 30)]


def test_country_call_keeps_every_job_it_returns():
    source = StubSource(
        {"A": [_job("1", "Jakarta")], "COUNTRY": [_job("9", "Indonesia"), _job("8", "Bali")]}
    )
    jobs = search_all(
        source, "devops", _plan("A", is_country_wide=True), max_age_hours=None, limit=30
    )
    assert [j["job_id"] for j in jobs] == ["1", "9", "8"]


def test_country_wide_plan_without_cities_makes_only_the_country_call():
    source = StubSource({"COUNTRY": [_job("9", "Surabaya")]})
    jobs = search_all(source, "devops", _plan(is_country_wide=True), max_age_hours=24, limit=5)
    assert [j["job_id"] for j in jobs] == ["9"]
    assert source.calls == [("devops", "COUNTRY", 24, 5)]


def test_plan_without_any_request_makes_no_call():
    source = StubSource({})
    assert search_all(source, "devops", _plan(), max_age_hours=None, limit=30) == []
    assert source.calls == []


def test_api_error_propagates_for_site_level_fallback():
    source = StubSource({"A": [_job("1", "Jakarta")], "B": ApiError("http_500")})
    with pytest.raises(ApiError):
        search_all(source, "devops", _plan("A", "B"), max_age_hours=None, limit=30)


def test_dedup_falls_back_to_url_then_title_company():
    a = _job(None, "Jakarta", url="https://x/1")
    b = _job(None, "Jakarta", url="https://x/1")
    c = _job(None, "Jakarta")
    d = _job(None, "Jakarta")
    assert dedup_jobs([a, b, c, d]) == [a, c]


def test_streams_are_interleaved_one_entry_at_a_time():
    interleaved = interleave_job_streams_round_robin([["a1", "a2", "a3"], [], ["c1", "c2"]])
    assert interleaved == ["a1", "c1", "a2", "c2", "a3"]


def test_interleaving_no_stream_gives_nothing():
    assert interleave_job_streams_round_robin([]) == []


def test_cities_are_interleaved_so_a_small_limit_keeps_every_city():
    source = StubSource(
        {
            "A": [_job("a1", "Jakarta"), _job("a2", "Jakarta"), _job("a3", "Jakarta")],
            "B": [_job("b1", "Bandung")],
            "COUNTRY": [_job("c1", "Indonesia"), _job("a1", "Jakarta")],
        }
    )
    jobs = search_all(
        source, "devops", _plan("A", "B", is_country_wide=True), max_age_hours=None, limit=3
    )
    assert [j["job_id"] for j in jobs] == ["a1", "b1", "c1", "a2", "a3"]
