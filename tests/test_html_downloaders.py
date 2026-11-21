from __future__ import annotations

from scraper.html_downloaders import (
    FallbackHtmlDownloader,
    HtmlDownloadAttempt,
    detect_challenge,
    looks_like_challenge,
)
from scraper.runner import scrape_site_for_keyword
from tests.runner_fakes import FakeScraper

SEARCH_URL = "https://glints.com/id/opportunities/jobs/explore?keyword=devops"
JOB_LIST_HTML = "<html><body><ul><li>Data Analyst</li></ul></body></html>"
LONG_PAGE_LENGTH = 5000


class FakeHtmlDownloader:
    def __init__(self, name: str, html: str | None, code: str, detail: str | None = None) -> None:
        self.name = name
        self.downloaded_urls: list[str] = []
        self._html = html
        self._code = code
        self._detail = detail

    def download_html(self, url: str) -> tuple[str | None, HtmlDownloadAttempt]:
        self.downloaded_urls.append(url)
        attempt = HtmlDownloadAttempt(downloader=self.name, code=self._code, detail=self._detail)
        return self._html, attempt


def test_attempt_to_dict_returns_exactly_downloader_code_and_detail():
    attempt = HtmlDownloadAttempt(downloader="curl_cffi", code="http_403", detail="blocked")

    attempt_as_dict = attempt.to_dict()

    assert attempt_as_dict == {"downloader": "curl_cffi", "code": "http_403", "detail": "blocked"}


def test_attempt_to_dict_keeps_a_missing_detail_as_none():
    attempt = HtmlDownloadAttempt(downloader="curl_cffi", code="ok")

    attempt_as_dict = attempt.to_dict()

    assert attempt_as_dict == {"downloader": "curl_cffi", "code": "ok", "detail": None}


def test_fallback_stops_at_the_first_downloader_that_returns_ok_html():
    first_downloader = FakeHtmlDownloader("first", JOB_LIST_HTML, "ok")
    second_downloader = FakeHtmlDownloader("second", "<html>second</html>", "ok")
    fallback_downloader = FallbackHtmlDownloader([first_downloader, second_downloader])

    download_result = fallback_downloader.download_html(SEARCH_URL)

    assert download_result.html == JOB_LIST_HTML
    assert download_result.attempts == (HtmlDownloadAttempt(downloader="first", code="ok"),)
    assert first_downloader.downloaded_urls == [SEARCH_URL]
    assert second_downloader.downloaded_urls == []


def test_fallback_tries_downloaders_in_the_given_order():
    blocked_downloader = FakeHtmlDownloader("blocked", None, "http_403", "forbidden")
    working_downloader = FakeHtmlDownloader("working", JOB_LIST_HTML, "ok")
    unused_downloader = FakeHtmlDownloader("unused", "<html>unused</html>", "ok")
    fallback_downloader = FallbackHtmlDownloader(
        [blocked_downloader, working_downloader, unused_downloader]
    )

    download_result = fallback_downloader.download_html(SEARCH_URL)

    assert download_result.html == JOB_LIST_HTML
    assert download_result.attempts == (
        HtmlDownloadAttempt(downloader="blocked", code="http_403", detail="forbidden"),
        HtmlDownloadAttempt(downloader="working", code="ok"),
    )
    assert blocked_downloader.downloaded_urls == [SEARCH_URL]
    assert working_downloader.downloaded_urls == [SEARCH_URL]
    assert unused_downloader.downloaded_urls == []


def test_fallback_falls_through_when_a_downloader_returns_no_html_with_ok_code():
    empty_downloader = FakeHtmlDownloader("empty", "", "ok")
    working_downloader = FakeHtmlDownloader("working", JOB_LIST_HTML, "ok")
    fallback_downloader = FallbackHtmlDownloader([empty_downloader, working_downloader])

    download_result = fallback_downloader.download_html(SEARCH_URL)

    assert download_result.html == JOB_LIST_HTML
    assert [attempt.downloader for attempt in download_result.attempts] == ["empty", "working"]


def test_fallback_falls_through_when_a_downloader_returns_html_with_a_non_ok_code():
    challenged_downloader = FakeHtmlDownloader("challenged", "<html>blocked</html>", "challenge")
    working_downloader = FakeHtmlDownloader("working", JOB_LIST_HTML, "ok")
    fallback_downloader = FallbackHtmlDownloader([challenged_downloader, working_downloader])

    download_result = fallback_downloader.download_html(SEARCH_URL)

    assert download_result.html == JOB_LIST_HTML
    assert [attempt.code for attempt in download_result.attempts] == ["challenge", "ok"]


def test_fallback_returns_no_html_and_every_attempt_when_all_downloaders_fail():
    timed_out_downloader = FakeHtmlDownloader("timed_out", None, "timeout")
    challenged_downloader = FakeHtmlDownloader("challenged", "<html>blocked</html>", "challenge")
    missing_downloader = FakeHtmlDownloader("missing", None, "not_installed", "no browser")
    fallback_downloader = FallbackHtmlDownloader(
        [timed_out_downloader, challenged_downloader, missing_downloader]
    )

    download_result = fallback_downloader.download_html(SEARCH_URL)

    assert download_result.html is None
    assert download_result.attempts == (
        HtmlDownloadAttempt(downloader="timed_out", code="timeout"),
        HtmlDownloadAttempt(downloader="challenged", code="challenge"),
        HtmlDownloadAttempt(downloader="missing", code="not_installed", detail="no browser"),
    )


def test_fallback_without_downloaders_returns_no_html_and_no_attempts():
    fallback_downloader = FallbackHtmlDownloader([])

    download_result = fallback_downloader.download_html(SEARCH_URL)

    assert download_result.html is None
    assert download_result.attempts == ()


def test_challenge_title_is_detected_even_on_a_long_page():
    long_challenge_page = "<html><head><title>Just a moment...</title></head>" + (
        "x" * LONG_PAGE_LENGTH
    )

    challenge_reason = detect_challenge(long_challenge_page)

    assert challenge_reason == "title=Just a moment..."
    assert looks_like_challenge(long_challenge_page) is True


def test_challenge_marker_on_a_short_page_is_detected():
    short_challenge_page = '<html><body><div class="cf-browser-verification"></div></body></html>'

    challenge_reason = detect_challenge(short_challenge_page)

    assert challenge_reason == "marker=cf-browser-verification"
    assert looks_like_challenge(short_challenge_page) is True


def test_challenge_marker_on_a_long_page_is_not_detected():
    long_page_with_marker = "<html><body>challenge-platform" + ("x" * LONG_PAGE_LENGTH)

    challenge_reason = detect_challenge(long_page_with_marker)

    assert challenge_reason is None
    assert looks_like_challenge(long_page_with_marker) is False


def test_normal_page_is_not_a_challenge():
    normal_page = "<html><head><title>Data Analyst Jobs</title></head>" + JOB_LIST_HTML

    challenge_reason = detect_challenge(normal_page)

    assert challenge_reason is None
    assert looks_like_challenge(normal_page) is False


def test_failed_search_html_download_reports_each_attempt_under_the_downloader_key():
    scraper = FakeScraper(name="glints", url=SEARCH_URL, limit=10, jobs=[])
    blocked_downloader = FakeHtmlDownloader("fake_downloader", None, "http_403", "forbidden")
    fallback_downloader = FallbackHtmlDownloader([blocked_downloader])

    payloads = scrape_site_for_keyword(
        scraper, fallback_downloader, "devops", frozenset({"title"}), None, {}
    )

    error_payload = payloads.filtered
    assert error_payload["error"] == "fetch failed"
    assert error_payload["attempts"][0]["downloader"] == "fake_downloader"
    assert error_payload["attempts"] == [
        {"downloader": "fake_downloader", "code": "http_403", "detail": "forbidden"}
    ]
    assert scraper.parsed_html_pages == []
