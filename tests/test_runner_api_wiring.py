from __future__ import annotations

from typing import Any, cast

import pytest
import yaml

from scraper import runner
from scraper.api.client import DEFAULT_DELAY_SECONDS, DETAIL_DELAY_SECONDS
from scraper.api.location_search_plan import LocationSearchPlan
from scraper.config_loader import ApiConfig, parse_job_settings_into_app_config
from scraper.runner import build_api_search_and_requirements_functions
from scraper.types import Job, empty_job
from tests.runner_fakes import build_html_downloader_returning

SEARCH_PAGE_WITHOUT_JOBS = "<html><body>no job cards</body></html>"


class RecordingSource:
    name = "stub"
    country_location = "COUNTRY"
    instances: list[RecordingSource] = []

    def __init__(self, client: Any) -> None:
        self.client = client
        self.searched: list[str | None] = []
        RecordingSource.instances.append(self)

    def search(self, keyword: str, location: str | None, max_age_hours: int | None, limit: int):
        self.searched.append(location)
        job = empty_job("stub", f"T-{location}", "C")
        job["job_id"] = str(location)
        return [job]

    def detail(self, job: Job) -> str | None:
        return f"detail via {self.client['delay']}"


TWO_CITIES_PLAN = LocationSearchPlan(city_values=("A", "B"), is_country_wide=False)


def _factory(**kwargs: Any) -> dict[str, Any]:
    return {"delay": kwargs.get("delay", DEFAULT_DELAY_SECONDS), "proxy": kwargs.get("proxy")}


def _build(api_config: ApiConfig, location_search_plan: LocationSearchPlan):
    RecordingSource.instances.clear()
    return build_api_search_and_requirements_functions(
        cast(Any, RecordingSource),
        api_config,
        "devops",
        location_search_plan=location_search_plan,
        proxy_url="http://p:1",
        max_age_hours=72,
        limit=30,
        build_api_client=_factory,
    )


def test_search_uses_site_delay_and_detail_uses_short_delay():
    search, detail = _build(ApiConfig(True, delay_seconds=(4.0, 6.0)), TWO_CITIES_PLAN)

    assert [j["job_id"] for j in search()] == ["A", "B"]
    assert detail(empty_job("stub", "T", "C")) == f"detail via {DETAIL_DELAY_SECONDS}"

    api_source_for_search, api_source_for_requirements = RecordingSource.instances
    assert api_source_for_search.client == {"delay": (4.0, 6.0), "proxy": "http://p:1"}
    assert api_source_for_requirements.client == {
        "delay": DETAIL_DELAY_SECONDS,
        "proxy": "http://p:1",
    }
    assert api_source_for_requirements.searched == []


def test_search_falls_back_to_default_delay():
    _build(ApiConfig(True), TWO_CITIES_PLAN)
    assert RecordingSource.instances[0].client["delay"] == DEFAULT_DELAY_SECONDS


def test_search_makes_one_request_per_city_then_the_country_request():
    search, _detail = _build(
        ApiConfig(True), LocationSearchPlan(city_values=("A",), is_country_wide=True)
    )

    assert [j["job_id"] for j in search()] == ["A", "COUNTRY"]
    assert RecordingSource.instances[0].searched == ["A", "COUNTRY"]


def test_scrape_all_sites_wires_api_functions_into_scrape_site_for_keyword(
    monkeypatch: pytest.MonkeyPatch,
):
    parsed_job_settings = yaml.safe_load(
        """
sites:
  jobstreet:
    limit: 3
    url_template: "https://id.jobstreet.com/id/{keyword_slug}-jobs"
    filter:
      location: [Jakarta, Bandung, Indonesia]
    api:
      delay_seconds: [4, 6]
  glints:
    enabled: false
    limit: 3
    url_template: "https://glints.com/id/opportunities/jobs/explore?keyword={keyword}"
"""
    )
    built: list[tuple[str, LocationSearchPlan, tuple[float, float] | None]] = []
    received: list[dict[str, Any]] = []

    def search() -> list[Job]:
        return []

    def detail(job: Job) -> str | None:
        return None

    def fake_build(build_api_source, api_config, keyword, **kwargs):
        built.append((keyword, kwargs["location_search_plan"], api_config.delay_seconds))
        return search, detail

    def fake_scrape_site_for_keyword(*args: Any, **kwargs: Any) -> runner.FilteredAndRawPayloads:
        received.append(kwargs)
        return runner.FilteredAndRawPayloads(
            filtered={"count": 0, "jobs": []}, raw={"count": 0, "jobs": []}
        )

    monkeypatch.setattr(runner, "build_api_search_and_requirements_functions", fake_build)
    monkeypatch.setattr(runner, "scrape_site_for_keyword", fake_scrape_site_for_keyword)

    assert (
        runner.scrape_all_sites(
            parse_job_settings_into_app_config(parsed_job_settings, None), keywords=["devops"]
        ).exit_code
        == 0
    )
    jobstreet_plan = LocationSearchPlan(
        city_values=("Jakarta Raya", "Bandung Jawa Barat"), is_country_wide=True
    )
    assert built == [("devops", jobstreet_plan, (4.0, 6.0))]
    assert received == [{"search_jobs_via_api": search, "read_requirements_via_api": detail}]


def test_scrape_all_sites_gives_each_scraper_the_plan_of_its_location_filter(
    monkeypatch: pytest.MonkeyPatch,
):
    parsed_job_settings = yaml.safe_load(
        """
sites:
  indeed:
    limit: 3
    url_template: "https://id.indeed.com/jobs?q={keyword_plus}&l=Indonesia"
    filter:
      location: [Tangerang Selatan, Indonesia]
"""
    )
    scraped_scrapers: list[Any] = []

    def fake_scrape_site_for_keyword(*args: Any, **kwargs: Any) -> runner.FilteredAndRawPayloads:
        scraped_scrapers.append(args[0])
        return runner.FilteredAndRawPayloads(
            filtered={"count": 0, "jobs": []}, raw={"count": 0, "jobs": []}
        )

    monkeypatch.setattr(runner, "scrape_site_for_keyword", fake_scrape_site_for_keyword)

    runner.scrape_all_sites(
        parse_job_settings_into_app_config(parsed_job_settings, None), keywords=["devops"]
    )

    assert len(scraped_scrapers) == 1
    assert scraped_scrapers[0].location_search_plan == LocationSearchPlan(
        city_values=("Tangerang",), is_country_wide=True
    )


def test_scrape_all_sites_skips_the_api_when_no_picked_location_has_a_search_value(
    monkeypatch: pytest.MonkeyPatch,
):
    parsed_job_settings = yaml.safe_load(
        """
sites:
  jobstreet:
    limit: 3
    url_template: "https://id.jobstreet.com/id/{keyword_slug}-jobs"
    filter:
      location: [Jakarta]
    api:
      enabled: true
"""
    )
    received: list[dict[str, Any]] = []

    def fake_scrape_site_for_keyword(*args: Any, **kwargs: Any) -> runner.FilteredAndRawPayloads:
        received.append(kwargs)
        return runner.FilteredAndRawPayloads(
            filtered={"count": 0, "jobs": []}, raw={"count": 0, "jobs": []}
        )

    monkeypatch.setattr(runner, "scrape_site_for_keyword", fake_scrape_site_for_keyword)
    monkeypatch.setattr(
        runner,
        "build_location_search_plan",
        lambda site_name, filter_locations: LocationSearchPlan((), False),
    )

    runner.scrape_all_sites(
        parse_job_settings_into_app_config(parsed_job_settings, None), keywords=["devops"]
    )

    assert received == [{"search_jobs_via_api": None, "read_requirements_via_api": None}]


def test_scrape_all_sites_uses_the_html_path_when_the_plan_of_an_html_site_has_no_request(
    monkeypatch: pytest.MonkeyPatch,
):
    parsed_job_settings = yaml.safe_load(
        """
sites:
  jobstreet:
    limit: 3
    url_template: "https://id.jobstreet.com/id/{keyword_slug}-jobs"
    filter:
      location: [Jakarta]
    api:
      enabled: true
"""
    )
    html_downloader = build_html_downloader_returning(SEARCH_PAGE_WITHOUT_JOBS)
    built_api_keywords: list[str] = []

    def search() -> list[Job]:
        return []

    def detail(job: Job) -> str | None:
        return None

    def fake_build(build_api_source, api_config, keyword, **kwargs):
        built_api_keywords.append(keyword)
        return search, detail

    monkeypatch.setattr(runner, "build_api_search_and_requirements_functions", fake_build)
    monkeypatch.setattr(runner, "FallbackHtmlDownloader", lambda downloaders: html_downloader)
    monkeypatch.setattr(
        runner,
        "build_location_search_plan",
        lambda site_name, filter_locations: LocationSearchPlan((), False),
    )

    scrape_summary = runner.scrape_all_sites(
        parse_job_settings_into_app_config(parsed_job_settings, None), keywords=["devops"]
    )

    jobstreet_payloads = scrape_summary.get_payloads_for_keyword_and_site("devops", "jobstreet")
    assert jobstreet_payloads is not None
    assert jobstreet_payloads.filtered["source"] == "html"
    assert jobstreet_payloads.filtered["fallback_reason"] is None
    assert built_api_keywords == []
    html_downloader.download_html.assert_called_once_with("https://id.jobstreet.com/id/devops-jobs")
