from __future__ import annotations

from typing import Any, cast

import pytest
import yaml

from scraper import runner
from scraper.api.client import DEFAULT_DELAY_SECONDS, DETAIL_DELAY_SECONDS
from scraper.config_loader import ApiConfig, parse_job_settings_into_app_config
from scraper.runner import build_api_search_and_requirements_functions
from scraper.types import Job, empty_job


class RecordingSource:
    name = "stub"
    country_location = None
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


def _factory(**kwargs: Any) -> dict[str, Any]:
    return {"delay": kwargs.get("delay", DEFAULT_DELAY_SECONDS), "proxy": kwargs.get("proxy")}


def _build(api_config: ApiConfig):
    RecordingSource.instances.clear()
    return build_api_search_and_requirements_functions(
        cast(Any, RecordingSource),
        api_config,
        "devops",
        proxy_url="http://p:1",
        max_age_hours=72,
        limit=30,
        build_api_client=_factory,
    )


def test_search_uses_site_delay_and_detail_uses_short_delay():
    search, detail = _build(ApiConfig(True, ("A", "B"), False, delay_seconds=(4.0, 6.0)))

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
    _build(ApiConfig(True, ("A",), False))
    assert RecordingSource.instances[0].client["delay"] == DEFAULT_DELAY_SECONDS


def test_scrape_all_sites_wires_api_functions_into_scrape_site_for_keyword(
    monkeypatch: pytest.MonkeyPatch,
):
    raw_config = yaml.safe_load(
        """
sites:
  jobstreet:
    limit: 3
    url_template: "https://id.jobstreet.com/id/{keyword_slug}-jobs"
    api:
      locations: [Jakarta Raya]
      delay_seconds: [4, 6]
  glints:
    enabled: false
    limit: 3
    url_template: "https://glints.com/id/opportunities/jobs/explore?keyword={keyword}"
"""
    )
    built: list[tuple[str, tuple[str, ...], tuple[float, float] | None]] = []
    received: list[dict[str, Any]] = []

    def search() -> list[Job]:
        return []

    def detail(job: Job) -> str | None:
        return None

    def fake_build(build_api_source, api_config, keyword, **kwargs):
        built.append((keyword, api_config.locations, api_config.delay_seconds))
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
            parse_job_settings_into_app_config(raw_config, None), keywords=["devops"]
        ).exit_code
        == 0
    )
    assert built == [("devops", ("Jakarta Raya",), (4.0, 6.0))]
    assert received == [{"search_jobs_via_api": search, "read_requirements_via_api": detail}]
