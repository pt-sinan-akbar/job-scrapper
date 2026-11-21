from __future__ import annotations

from scraper import runner
from tests.runner_fakes import FakeScraper, build_html_downloader_returning


def _job(title: str, location: str) -> dict:
    return {"title": title, "company": "ACME", "url": f"https://x/{title}", "location": location}


def _scraper_parsing(jobs: list[dict]) -> FakeScraper:
    return FakeScraper(name="fake", url="https://example.test/search", limit=5, jobs=jobs)


def test_scrape_site_for_keyword_returns_raw_before_filter():
    scraper = _scraper_parsing(
        [
            _job("A", "Jakarta"),
            _job("B", "Jakarta"),
            _job("C", "Surabaya"),
        ]
    )

    result = runner.scrape_site_for_keyword(
        scraper,
        build_html_downloader_returning("<html>ok</html>"),
        "data analyst",
        frozenset({"title", "company", "url", "location"}),
        None,
        {"location": ["jakarta"]},
    )

    assert result.raw["count"] == 3
    assert {j["title"] for j in result.raw["jobs"]} == {"A", "B", "C"}
    assert result.filtered["count"] == 2
    assert {j["title"] for j in result.filtered["jobs"]} == {"A", "B"}


def test_scrape_site_for_keyword_returns_empty_raw_when_html_download_fails():
    scraper = _scraper_parsing([_job("A", "Jakarta")])
    fields = frozenset({"title", "company", "url", "location"})

    result = runner.scrape_site_for_keyword(
        scraper, build_html_downloader_returning(""), "data analyst", fields, None, {}
    )

    assert result.raw == {
        "keyword": "data analyst",
        "count": 0,
        "jobs": [],
        "error": "fetch failed",
    }
    assert result.filtered["error"] == "fetch failed"


def test_scrape_site_for_keyword_saves_no_html(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    scraper = _scraper_parsing([_job("A", "Jakarta")])

    runner.scrape_site_for_keyword(
        scraper,
        build_html_downloader_returning("<html>ok</html>"),
        "data analyst",
        frozenset({"title"}),
        None,
        {},
    )

    assert list(tmp_path.rglob("*.html")) == []
    assert not (tmp_path / "output").exists()
