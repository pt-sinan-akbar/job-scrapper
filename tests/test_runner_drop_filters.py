from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import pytest

from scraper.runner import scrape_site_for_keyword
from scraper.types import Job, empty_job
from tests.runner_fakes import FakeScraper, build_html_downloader_returning

LABEL = "fake:data-analyst"
FIELDS = frozenset({"title", "location"})
JAKARTA_FILTER = {"location": ["jakarta"]}


def _build_job(title: str, location: str, posted_at: str | None) -> Job:
    job = empty_job("fake", title, "Acme")
    job["location"] = location
    job["url"] = f"https://example.test/{title.replace(' ', '-')}"
    job["posted_at"] = posted_at
    return job


def _compute_hours_ago(hours: int) -> str:
    return (datetime.now(UTC) - timedelta(hours=hours)).isoformat()


def _scrape_jobs(
    jobs: list[Job], max_age_hours: int | None, content_filter: dict[str, list[str]]
) -> list[str]:
    scraper = FakeScraper(name="fake", url="https://example.test/search", limit=10, jobs=jobs)
    payloads = scrape_site_for_keyword(
        scraper,
        build_html_downloader_returning("<html>ok</html>"),
        "data analyst",
        FIELDS,
        max_age_hours,
        content_filter,
    )
    kept_job_titles: list[str] = []
    for kept_job in payloads.filtered["jobs"]:
        kept_job_titles.append(kept_job["title"])
    return kept_job_titles


def _list_lines_starting_with(log_capture: pytest.LogCaptureFixture, line_start: str) -> list[str]:
    matching_lines: list[str] = []
    for message in log_capture.messages:
        if message.startswith(line_start):
            matching_lines.append(message)
    return matching_lines


@pytest.fixture
def debug_log_records(scraper_log_records: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    scraper_log_records.set_level(logging.DEBUG, logger="job-scraper")
    return scraper_log_records


def test_stale_job_is_dropped_with_its_posted_at_and_cutoff(
    debug_log_records: pytest.LogCaptureFixture,
):
    stale_posted_at = _compute_hours_ago(100)
    jobs = [
        _build_job("Old Role", "Jakarta", stale_posted_at),
        _build_job("New Role", "Jakarta", _compute_hours_ago(1)),
    ]

    kept_job_titles = _scrape_jobs(jobs, 24, {})

    assert kept_job_titles == ["New Role"]
    stale_lines = _list_lines_starting_with(
        debug_log_records, f"[{LABEL}] drop stale: 'Old Role' posted_at={stale_posted_at} < cutoff="
    )
    assert len(stale_lines) == 1


def test_job_outside_the_filter_is_dropped_with_the_filter_reason(
    debug_log_records: pytest.LogCaptureFixture,
):
    jobs = [
        _build_job("Surabaya Role", "Surabaya", None),
        _build_job("Jakarta Role", "Jakarta", None),
    ]

    kept_job_titles = _scrape_jobs(jobs, None, JAKARTA_FILTER)

    assert kept_job_titles == ["Jakarta Role"]
    assert (
        f"[{LABEL}] drop filter: 'Surabaya Role' location='Surabaya' not in ['jakarta']"
        in debug_log_records.messages
    )


def test_job_both_stale_and_outside_the_filter_is_dropped_as_stale(
    debug_log_records: pytest.LogCaptureFixture,
):
    jobs = [_build_job("Old Surabaya Role", "Surabaya", _compute_hours_ago(100))]

    kept_job_titles = _scrape_jobs(jobs, 24, JAKARTA_FILTER)

    assert kept_job_titles == []
    assert len(_list_lines_starting_with(debug_log_records, f"[{LABEL}] drop stale:")) == 1
    assert _list_lines_starting_with(debug_log_records, f"[{LABEL}] drop filter:") == []


@pytest.mark.parametrize("posted_at", [None, "yesterday"])
def test_job_without_a_readable_posted_at_is_kept_when_max_age_is_set(posted_at: str | None):
    kept_job_titles = _scrape_jobs([_build_job("Undated Role", "Jakarta", posted_at)], 24, {})

    assert kept_job_titles == ["Undated Role"]


def test_no_drop_summary_is_logged_without_max_age_and_filter(
    debug_log_records: pytest.LogCaptureFixture,
):
    jobs = [_build_job("Old Surabaya Role", "Surabaya", _compute_hours_ago(100))]

    kept_job_titles = _scrape_jobs(jobs, None, {})

    assert kept_job_titles == ["Old Surabaya Role"]
    drop_lines: list[str] = []
    for message in debug_log_records.messages:
        if "dropped" in message or "drop " in message:
            drop_lines.append(message)
    assert drop_lines == []


def test_one_summary_line_counts_stale_and_filter_drops(
    debug_log_records: pytest.LogCaptureFixture,
):
    jobs = [
        _build_job("Old Role", "Jakarta", _compute_hours_ago(100)),
        _build_job("Surabaya Role", "Surabaya", _compute_hours_ago(1)),
        _build_job("Jakarta Role", "Jakarta", _compute_hours_ago(1)),
    ]

    kept_job_titles = _scrape_jobs(jobs, 24, JAKARTA_FILTER)

    assert kept_job_titles == ["Jakarta Role"]
    summary_lines = _list_lines_starting_with(debug_log_records, f"[{LABEL}] max_age=24h cutoff=")
    assert len(summary_lines) == 1
    assert summary_lines[0].endswith(
        "filter={'location': ['jakarta']} kept 1/3 (dropped 1 stale, 1 filter)"
    )


def test_summary_line_without_max_age_says_it_is_off(
    debug_log_records: pytest.LogCaptureFixture,
):
    _scrape_jobs([_build_job("Jakarta Role", "Jakarta", None)], None, JAKARTA_FILTER)

    assert (
        f"[{LABEL}] max_age=off cutoff=off filter={{'location': ['jakarta']}} "
        "kept 1/1 (dropped 0 stale, 0 filter)"
    ) in debug_log_records.messages


def test_summary_line_cutoff_is_a_utc_midnight(debug_log_records: pytest.LogCaptureFixture):
    _scrape_jobs([_build_job("Jakarta Role", "Jakarta", None)], 72, {})

    summary_lines = _list_lines_starting_with(debug_log_records, f"[{LABEL}] max_age=72h cutoff=")
    assert len(summary_lines) == 1
    assert "T00:00:00+00:00 filter=" in summary_lines[0]
