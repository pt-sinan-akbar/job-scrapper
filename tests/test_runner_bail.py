from __future__ import annotations

from scraper.runner import scrape_site_for_keyword
from tests.runner_fakes import FakeScraper, build_html_downloader_returning


def test_scrape_site_for_keyword_bails_when_html_required_and_missing():
    scraper = FakeScraper(name="glints", url="https://glints.com/x", limit=10, jobs=[])
    html_downloader = build_html_downloader_returning(None)

    result = scrape_site_for_keyword(
        scraper=scraper,
        html_downloader=html_downloader,
        keyword="data analyst",
        fields=frozenset({"title"}),
        max_age_hours=None,
        content_filter={},
    )

    assert result.filtered == {
        "error": "fetch failed",
        "url": "https://glints.com/x",
        "keyword": "data analyst",
        "attempts": [],
        "source": "html",
        "fallback_reason": None,
    }
    assert scraper.parsed_html_pages == []


def test_scrape_site_for_keyword_skips_bail_for_indeed_style_scraper():
    fake_job = {
        "site": "indeed",
        "matched_keyword": "data analyst",
        "title": "API job",
        "company": "ACME",
        "url": "https://id.indeed.com/viewjob?jk=1",
        "requirements": "from API",
        "posted_at": None,
        "posted_date": None,
    }
    scraper = FakeScraper(
        name="indeed",
        url="https://id.indeed.com/jobs?q=x",
        limit=10,
        jobs=[fake_job],
        requires_search_html=False,
    )
    html_downloader = build_html_downloader_returning(None)

    result = scrape_site_for_keyword(
        scraper=scraper,
        html_downloader=html_downloader,
        keyword="data analyst",
        fields=frozenset({"title", "url", "requirements"}),
        max_age_hours=None,
        content_filter={},
    )

    assert scraper.parsed_html_pages == [""]
    html_downloader.download_html.assert_not_called()
    out = result.filtered
    assert out["count"] == 1
    assert out["jobs"][0]["title"] == "API job"
    assert out["jobs"][0]["requirements"] == "from API"


def test_scraper_making_its_own_request_never_gets_the_search_page():
    scraper = FakeScraper(
        name="indeed",
        url="https://id.indeed.com/jobs?q=x",
        limit=10,
        jobs=[],
        requires_search_html=False,
    )
    html_downloader = build_html_downloader_returning("<html>ok</html>")

    payloads = scrape_site_for_keyword(
        scraper=scraper,
        html_downloader=html_downloader,
        keyword="data analyst",
        fields=frozenset({"title"}),
        max_age_hours=None,
        content_filter={},
    )

    assert scraper.parsed_html_pages == [""]
    html_downloader.download_html.assert_not_called()
    assert payloads.filtered["count"] == 0
