from __future__ import annotations

from unittest.mock import MagicMock

from scraper import runner


def _job(title: str, location: str) -> dict:
    return {"title": title, "company": "ACME", "url": f"https://x/{title}", "location": location}


def _scraper() -> MagicMock:
    scraper = MagicMock()
    scraper.name = "fake"
    scraper.url = "https://example.test/search"
    scraper.limit = 5
    scraper.requires_search_html = True
    scraper.api_only = False
    return scraper


def _fetcher(html: str) -> MagicMock:
    fetcher = MagicMock()
    fetcher.fetch.return_value.html = html
    fetcher.fetch.return_value.attempts = []
    return fetcher


def test_run_one_returns_raw_before_filter():
    scraper = _scraper()
    scraper.parse.return_value = [
        _job("A", "Jakarta"),
        _job("B", "Jakarta"),
        _job("C", "Surabaya"),
    ]

    result = runner.run_one(
        scraper,
        _fetcher("<html>ok</html>"),
        "data analyst",
        frozenset({"title", "company", "url", "location"}),
        None,
        {"location": ["jakarta"]},
    )

    assert result.raw["count"] == 3
    assert {j["title"] for j in result.raw["jobs"]} == {"A", "B", "C"}
    assert result.filtered["count"] == 2
    assert {j["title"] for j in result.filtered["jobs"]} == {"A", "B"}


def test_run_one_returns_empty_raw_on_fetch_failure():
    scraper = _scraper()
    scraper.parse.return_value = [_job("A", "Jakarta")]
    fields = frozenset({"title", "company", "url", "location"})

    result = runner.run_one(scraper, _fetcher(""), "data analyst", fields, None, {})

    assert result.raw == {
        "keyword": "data analyst",
        "count": 0,
        "jobs": [],
        "error": "fetch failed",
    }
    assert result.filtered["error"] == "fetch failed"


def test_run_one_saves_no_html(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    scraper = _scraper()
    scraper.parse.return_value = [_job("A", "Jakarta")]

    runner.run_one(
        scraper, _fetcher("<html>ok</html>"), "data analyst", frozenset({"title"}), None, {}
    )

    assert list(tmp_path.rglob("*.html")) == []
    assert not (tmp_path / "output").exists()
