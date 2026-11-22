from __future__ import annotations

import pytest
import yaml

from scraper.api.registry import API_SOURCES
from scraper.config_loader import (
    ApiConfig,
    AppConfig,
    ConfigError,
    parse_job_settings_into_app_config,
    validate_job_settings,
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
      enabled: false
      delay_seconds: [1, 2]
""",
    ).find_site_config("jobstreet")
    assert site is not None
    assert site.api == ApiConfig(enabled=False, delay_seconds=(1.0, 2.0))


def test_missing_api_block_is_none():
    site = _parse_app_config_with_extra_yaml("").find_site_config("jobstreet")
    assert site is not None
    assert site.api is None


def test_api_defaults():
    site = _parse_app_config_with_extra_yaml("    api: {}\n").find_site_config("jobstreet")
    assert site is not None
    assert site.api == ApiConfig(enabled=True)


def test_api_config_has_no_locations_or_country_wide():
    api_config = ApiConfig(enabled=True)

    assert not hasattr(api_config, "locations")
    assert not hasattr(api_config, "country_wide")


@pytest.mark.parametrize(
    "old_api_keys",
    [
        "      locations: [Jakarta Raya, Bandung Jawa Barat]\n      country_wide: true\n",
        "      locations: Jakarta\n",
        "      locations: [Remote]\n      country_wide: false\n",
    ],
)
def test_old_saved_locations_and_country_wide_are_ignored_silently(
    old_api_keys: str, scraper_log_records: pytest.LogCaptureFixture
):
    site = _parse_app_config_with_extra_yaml(
        "    api:\n      enabled: true\n" + old_api_keys
    ).find_site_config("jobstreet")

    assert site is not None
    assert site.api == ApiConfig(enabled=True)
    assert scraper_log_records.messages == []


def test_old_saved_locations_and_country_wide_pass_validation():
    settings = yaml.safe_load(
        BASE + "    api:\n      locations: [Jakarta Raya]\n      country_wide: true\n"
    )

    validate_job_settings(settings)


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
      enabled: true
"""
        ),
        None,
    )

    site = config.find_site_config("upwork")
    assert site is not None
    assert site.filter == {}
    assert site.limit == 30
    assert site.max_age_hours is None
    assert site.api == ApiConfig(enabled=True)
