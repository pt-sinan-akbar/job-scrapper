from __future__ import annotations

from typing import Any

import pytest
import yaml

from scraper import runner
from scraper.api.location_search_plan import LocationSearchPlan
from scraper.config_loader import AppConfig, parse_job_settings_into_app_config
from scraper.types import Job

JOBSTREET_WITH_SAVED_JAKARTA = """
sites:
  jobstreet:
    limit: 3
    url_template: "https://id.jobstreet.com/id/{keyword_slug}-jobs"
    filter:
      location: [Jakarta]
    api:
      enabled: true
"""

INDEED_WITH_SAVED_JAKARTA = """
sites:
  indeed:
    limit: 3
    url_template: "https://id.indeed.com/jobs?q={keyword_plus}&l=Indonesia"
    filter:
      location: [Jakarta]
"""


class PairRecorder:
    def __init__(self) -> None:
        self.api_plans: list[LocationSearchPlan] = []
        self.scraper_plans: list[LocationSearchPlan | None] = []
        self.content_filters: list[dict[str, list[str]]] = []

    def build_api_functions(self, build_api_source, api_config, keyword, **kwargs):
        self.api_plans.append(kwargs["location_search_plan"])
        return self.search_jobs, self.read_requirements

    def scrape_site_for_keyword(self, *args: Any, **kwargs: Any) -> runner.FilteredAndRawPayloads:
        self.scraper_plans.append(args[0].location_search_plan)
        self.content_filters.append(args[5])
        return runner.FilteredAndRawPayloads(
            filtered={"count": 0, "jobs": []}, raw={"count": 0, "jobs": []}
        )

    def search_jobs(self) -> list[Job]:
        return []

    def read_requirements(self, job: Job) -> str | None:
        return None


@pytest.fixture
def pair_recorder(monkeypatch: pytest.MonkeyPatch) -> PairRecorder:
    recorder = PairRecorder()
    monkeypatch.setattr(
        runner, "build_api_search_and_requirements_functions", recorder.build_api_functions
    )
    monkeypatch.setattr(runner, "scrape_site_for_keyword", recorder.scrape_site_for_keyword)
    return recorder


def test_requested_city_picks_the_api_search_city_instead_of_the_saved_filter(
    pair_recorder: PairRecorder,
):
    runner.scrape_all_sites(
        _build_config(JOBSTREET_WITH_SAVED_JAKARTA),
        keywords=["devops"],
        requested_location="bandung",
    )

    bandung_plan = LocationSearchPlan(city_values=("Bandung Jawa Barat",), is_country_wide=False)
    assert pair_recorder.api_plans == [bandung_plan]
    assert pair_recorder.scraper_plans == [bandung_plan]


def test_requested_location_leaves_the_saved_filter_as_the_content_filter(
    pair_recorder: PairRecorder,
):
    runner.scrape_all_sites(
        _build_config(JOBSTREET_WITH_SAVED_JAKARTA),
        keywords=["devops"],
        requested_location="bandung",
    )

    assert pair_recorder.content_filters == [{"location": ["jakarta"]}]


def test_requested_country_searches_country_wide_only(pair_recorder: PairRecorder):
    runner.scrape_all_sites(
        _build_config(JOBSTREET_WITH_SAVED_JAKARTA),
        keywords=["devops"],
        requested_location="Indonesia",
    )

    assert pair_recorder.api_plans == [LocationSearchPlan(city_values=(), is_country_wide=True)]


def test_absent_requested_location_keeps_the_plan_of_the_saved_filter(
    pair_recorder: PairRecorder,
):
    runner.scrape_all_sites(
        _build_config(JOBSTREET_WITH_SAVED_JAKARTA),
        keywords=["devops"],
        requested_location=None,
    )

    jakarta_plan = LocationSearchPlan(city_values=("Jakarta Raya",), is_country_wide=False)
    assert pair_recorder.api_plans == [jakarta_plan]
    assert pair_recorder.content_filters == [{"location": ["jakarta"]}]


def test_indeed_gets_the_plan_of_the_requested_city(pair_recorder: PairRecorder):
    runner.scrape_all_sites(
        _build_config(INDEED_WITH_SAVED_JAKARTA),
        keywords=["devops"],
        requested_location="tangerang selatan",
    )

    assert pair_recorder.scraper_plans == [
        LocationSearchPlan(city_values=("Tangerang",), is_country_wide=False)
    ]
    assert pair_recorder.content_filters == [{"location": ["jakarta"]}]


def _build_config(job_settings_yaml: str) -> AppConfig:
    return parse_job_settings_into_app_config(yaml.safe_load(job_settings_yaml), None)
