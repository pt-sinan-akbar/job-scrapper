from __future__ import annotations

from concurrent.futures import Future

import pytest

from scraper.runner import (
    _read_future_result_or_none,
    _read_requirements_from_job_page,
)
from scraper.sites.linkedin import LinkedinScraper
from scraper.types import Job, empty_job
from tests.log_lines import list_log_lines_containing, list_warning_or_above_log_lines
from tests.runner_fakes import build_html_downloader_returning

JOB_PAGE_HTML = "<div class='show-more-less-html__markup'>Five years of Python</div>"


def _linkedin_scraper() -> LinkedinScraper:
    return LinkedinScraper(url="https://www.linkedin.com/jobs/search?keywords=python", limit=10)


def _job_with_url(url: str | None) -> Job:
    job = empty_job("linkedin", "Backend Engineer", "Acme")
    job["url"] = url
    return job


def test_job_page_on_an_allowed_host_is_downloaded_and_parsed():
    job_url = "https://www.linkedin.com/jobs/view/123"
    html_downloader = build_html_downloader_returning(JOB_PAGE_HTML)

    requirements = _read_requirements_from_job_page(
        _job_with_url(job_url), html_downloader, _linkedin_scraper()
    )

    assert requirements is not None
    assert "Five years of Python" in requirements
    html_downloader.download_html.assert_called_once_with(job_url)


@pytest.mark.parametrize(
    "job_url",
    [
        "https://evil.example.com/jobs/view/123",
        "https://www.linkedin.com.evil.example.com/jobs/view/123",
        "https://evil.example.com/?next=www.linkedin.com",
        "http://169.254.169.254/latest/meta-data",
    ],
)
def test_job_page_on_a_host_outside_the_allowed_hosts_is_never_downloaded(job_url: str):
    html_downloader = build_html_downloader_returning(JOB_PAGE_HTML)

    requirements = _read_requirements_from_job_page(
        _job_with_url(job_url), html_downloader, _linkedin_scraper()
    )

    assert requirements is None
    html_downloader.download_html.assert_not_called()


@pytest.mark.parametrize("job_url", [None, ""])
def test_job_without_a_url_is_never_downloaded(job_url: str | None):
    html_downloader = build_html_downloader_returning(JOB_PAGE_HTML)

    requirements = _read_requirements_from_job_page(
        _job_with_url(job_url), html_downloader, _linkedin_scraper()
    )

    assert requirements is None
    html_downloader.download_html.assert_not_called()


@pytest.mark.parametrize(
    "job_url",
    ["not a url", "/jobs/view/123", "www.linkedin.com/jobs/view/123", "http://[not-an-ip/jobs"],
)
def test_job_with_a_url_that_has_no_readable_host_is_never_downloaded(job_url: str):
    html_downloader = build_html_downloader_returning(JOB_PAGE_HTML)

    requirements = _read_requirements_from_job_page(
        _job_with_url(job_url), html_downloader, _linkedin_scraper()
    )

    assert requirements is None
    html_downloader.download_html.assert_not_called()


def test_job_page_that_downloads_no_html_gives_no_requirements():
    html_downloader = build_html_downloader_returning(None)

    requirements = _read_requirements_from_job_page(
        _job_with_url("https://www.linkedin.com/jobs/view/123"),
        html_downloader,
        _linkedin_scraper(),
    )

    assert requirements is None


def test_future_that_raised_reads_as_none_and_logs_a_warning(
    scraper_log_records: pytest.LogCaptureFixture,
):
    failed_future: Future[str | None] = Future()
    failed_future.set_exception(RuntimeError("job page download crashed"))

    requirements = _read_future_result_or_none(failed_future, "linkedin")

    assert requirements is None
    assert "[linkedin] requirements read crashed (RuntimeError)" in scraper_log_records.messages
    warning_or_above_log_lines = list_warning_or_above_log_lines(scraper_log_records)
    assert list_log_lines_containing(warning_or_above_log_lines, "job page download crashed") == []


def test_future_that_finished_reads_as_its_value():
    finished_future: Future[str | None] = Future()
    finished_future.set_result("Five years of Python")

    requirements = _read_future_result_or_none(finished_future, "linkedin")

    assert requirements == "Five years of Python"
