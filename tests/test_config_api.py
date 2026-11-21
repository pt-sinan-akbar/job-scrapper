from __future__ import annotations

import pytest
import yaml

from scraper.api.registry import API_SOURCES
from scraper.config_loader import (
    ApiConfig,
    AppConfig,
    ConfigError,
    parse_job_settings_into_app_config,
)

BASE = """
sites:
  jobstreet:
    limit: 3
    url_template: "https://id.jobstreet.com/id/{keyword_slug}-jobs"
"""


def _parse_app_config_with_extra_yaml(extra: str) -> AppConfig:
    return parse_job_settings_into_app_config(yaml.safe_load(BASE + extra), None)


def test_api_block_parsed():
    site = _parse_app_config_with_extra_yaml(
        """    api:
      enabled: true
      locations: [Jakarta Raya, Bandung Jawa Barat]
      country_wide: true
""",
    ).find_site_config("jobstreet")
    assert site is not None
    assert site.api == ApiConfig(
        enabled=True, locations=("Jakarta Raya", "Bandung Jawa Barat"), country_wide=True
    )


def test_missing_api_block_is_none():
    site = _parse_app_config_with_extra_yaml("").find_site_config("jobstreet")
    assert site is not None
    assert site.api is None


def test_api_defaults():
    site = _parse_app_config_with_extra_yaml("    api: {}\n").find_site_config("jobstreet")
    assert site is not None
    assert site.api == ApiConfig(enabled=True, locations=(), country_wide=False)


def test_locations_must_be_list_of_strings():
    with pytest.raises(ConfigError, match="sites.jobstreet.api.locations"):
        _parse_app_config_with_extra_yaml("    api:\n      locations: Jakarta\n")


def test_registry_has_api_sites():
    assert set(API_SOURCES) == {"jobstreet", "glints", "linkedin", "upwork"}


def test_delay_seconds_parsed():
    site = _parse_app_config_with_extra_yaml(
        "    api:\n      delay_seconds: [4, 6]\n"
    ).find_site_config("jobstreet")
    assert site is not None
    assert site.api is not None
    assert site.api.delay_seconds == (4.0, 6.0)


def test_delay_seconds_defaults_to_none():
    site = _parse_app_config_with_extra_yaml("    api: {}\n").find_site_config("jobstreet")
    assert site is not None
    assert site.api is not None
    assert site.api.delay_seconds is None


@pytest.mark.parametrize("bad", ["5", "[6, 4]", "[-1, 2]", "[1, 2, 3]", "[a, b]"])
def test_delay_seconds_must_be_valid_range(bad: str):
    with pytest.raises(ConfigError, match="sites.jobstreet.api.delay_seconds"):
        _parse_app_config_with_extra_yaml(f"    api:\n      delay_seconds: {bad}\n")


def test_upwork_site_keeps_its_own_empty_filter_and_limit():
    config = parse_job_settings_into_app_config(
        yaml.safe_load(
            """
sites:
  upwork:
    limit: 30
    filter: {}
    url_template: "https://www.upwork.com/nx/search/jobs/?q={keyword}&sort=recency"
    api:
      locations: [Remote]
"""
        ),
        None,
    )

    site = config.find_site_config("upwork")
    assert site is not None
    assert site.filter == {}
    assert site.limit == 30
    assert site.max_age_hours is None
    assert site.api is not None
    assert site.api.locations == ("Remote",)
