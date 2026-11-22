from __future__ import annotations

from typing import Any

import pytest
import yaml

from scraper import runner
from scraper.config_loader import AppConfig, parse_job_settings_into_app_config
from scraper.types import Job

JOBSTREET_WITH_SAVED_24_HOURS = """
sites:
  jobstreet:
    limit: 3
    max_age_hours: 24
    url_template: "https://id.jobstreet.com/id/{keyword_slug}-jobs"
    filter:
      location: [Jakarta]
    api:
      enabled: true
"""


class MaxAgeRecorder:
    def __init__(self) -> None:
        self.api_max_age_hours: list[int | None] = []
        self.cutoff_max_age_hours: list[int | None] = []

    def build_api_functions(self, build_api_source, api_config, keyword, **kwargs):
        self.api_max_age_hours.append(kwargs["max_age_hours"])
        return self.search_jobs, self.read_requirements

    def scrape_site_for_keyword(self, *args: Any, **kwargs: Any) -> runner.FilteredAndRawPayloads:
        self.cutoff_max_age_hours.append(args[4])
        return runner.FilteredAndRawPayloads(
            filtered={"count": 0, "jobs": []}, raw={"count": 0, "jobs": []}
        )

    def search_jobs(self) -> list[Job]:
        return []

    def read_requirements(self, job: Job) -> str | None:
        return None


@pytest.fixture
def max_age_recorder(monkeypatch: pytest.MonkeyPatch) -> MaxAgeRecorder:
    recorder = MaxAgeRecorder()
    monkeypatch.setattr(
        runner, "build_api_search_and_requirements_functions", recorder.build_api_functions
    )
    monkeypatch.setattr(runner, "scrape_site_for_keyword", recorder.scrape_site_for_keyword)
    return recorder


def test_requested_max_age_replaces_the_saved_one_for_the_api_search_and_the_cutoff(
    max_age_recorder: MaxAgeRecorder,
):
    runner.scrape_all_sites(
        _build_config(JOBSTREET_WITH_SAVED_24_HOURS),
        keywords=["devops"],
        requested_max_age_hours=168,
    )

    assert max_age_recorder.api_max_age_hours == [168]
    assert max_age_recorder.cutoff_max_age_hours == [168]


def test_absent_requested_max_age_keeps_the_saved_one(max_age_recorder: MaxAgeRecorder):
    runner.scrape_all_sites(
        _build_config(JOBSTREET_WITH_SAVED_24_HOURS),
        keywords=["devops"],
        requested_max_age_hours=None,
    )

    assert max_age_recorder.api_max_age_hours == [24]
    assert max_age_recorder.cutoff_max_age_hours == [24]


def test_requested_max_age_leaves_the_saved_config_untouched(max_age_recorder: MaxAgeRecorder):
    config = _build_config(JOBSTREET_WITH_SAVED_24_HOURS)

    runner.scrape_all_sites(config, keywords=["devops"], requested_max_age_hours=720)

    saved_site_config = config.find_site_config("jobstreet")
    assert saved_site_config is not None
    assert saved_site_config.max_age_hours == 24


def _build_config(job_settings_yaml: str) -> AppConfig:
    return parse_job_settings_into_app_config(yaml.safe_load(job_settings_yaml), None)
