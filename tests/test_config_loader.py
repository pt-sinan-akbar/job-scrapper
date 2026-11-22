from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from scraper import config_loader
from scraper.config_loader import (
    CONCURRENCY_ENV_VAR,
    DEFAULT_CONCURRENCY,
    PROXY_ENV_VAR,
    ConfigError,
    parse_job_settings_into_app_config,
    read_concurrency_from_env,
    read_proxy_url_from_env,
    refuse_unknown_filter_locations,
    validate_job_settings,
)

JOBSTREET_URL = "https://id.jobstreet.com/id/{keyword_slug}-jobs"
SETTINGS = {
    "sites": {"jobstreet": {"limit": 3, "url_template": JOBSTREET_URL}},
}


def _with_site(**site: object) -> dict:
    return {**SETTINGS, "sites": {"jobstreet": {"url_template": JOBSTREET_URL, **site}}}


def test_parse_job_settings_into_app_config_builds_config_with_proxy():
    config = parse_job_settings_into_app_config(SETTINGS, "socks5://localhost:1080")

    assert config.proxy is not None
    assert config.proxy.url == "socks5://localhost:1080"


def test_parse_job_settings_into_app_config_without_proxy():
    assert parse_job_settings_into_app_config(SETTINGS, None).proxy is None


def test_config_has_no_global_job_values():
    config = parse_job_settings_into_app_config(SETTINGS, None)

    for name in ("limit", "concurrency", "max_age_hours", "filter", "output_dir", "keywords"):
        assert not hasattr(config, name)


def test_site_keeps_its_own_values():
    site = parse_job_settings_into_app_config(
        _with_site(limit=7, max_age_hours=24, filter={"location": ["Jakarta"]}), None
    ).find_site_config("jobstreet")

    assert site is not None
    assert site.limit == 7
    assert site.max_age_hours == 24
    assert site.filter == {"location": ["jakarta"]}


def test_site_without_age_or_filter_has_no_cut():
    site = parse_job_settings_into_app_config(SETTINGS, None).find_site_config("jobstreet")

    assert site is not None
    assert site.max_age_hours is None
    assert site.filter == {}


def test_global_values_never_reach_a_site():
    raw = {**SETTINGS, "limit": 9, "max_age_hours": 72, "filter": {"location": ["jakarta"]}}

    site = parse_job_settings_into_app_config(raw, None).find_site_config("jobstreet")

    assert site is not None
    assert site.limit == 3
    assert site.max_age_hours is None
    assert site.filter == {}


def test_site_limit_is_required():
    with pytest.raises(ConfigError, match="sites.jobstreet.limit is required"):
        parse_job_settings_into_app_config(_with_site(), None)


@pytest.mark.parametrize("value", [None, 0, 201, "3", True, 2.5])
def test_site_limit_must_be_a_whole_number_in_range(value: object):
    with pytest.raises(ConfigError, match="sites.jobstreet.limit"):
        parse_job_settings_into_app_config(_with_site(limit=value), None)


@pytest.mark.parametrize("value", [1, 200])
def test_site_limit_accepts_the_range_ends(value: int):
    site = parse_job_settings_into_app_config(_with_site(limit=value), None).find_site_config(
        "jobstreet"
    )

    assert site is not None
    assert site.limit == value


@pytest.mark.parametrize("key", ["limit", "concurrency", "max_age_hours", "filter"])
def test_validate_job_settings_refuses_global_job_values(key: str):
    with pytest.raises(ConfigError, match=f"not a job setting: {key}"):
        validate_job_settings({**SETTINGS, key: 3})


def test_validate_job_settings_refuses_keywords():
    with pytest.raises(ConfigError, match="not a job setting: keywords"):
        validate_job_settings({**SETTINGS, "keywords": ["devops"]})


def test_parse_job_settings_into_app_config_ignores_stored_keywords():
    config = parse_job_settings_into_app_config({**SETTINGS, "keywords": ["devops"]}, None)

    assert not hasattr(config, "keywords")
    assert not hasattr(config, "keyword")


def test_parse_job_settings_into_app_config_checks_url_templates_without_keywords():
    with pytest.raises(ConfigError, match="unknown placeholder"):
        parse_job_settings_into_app_config(
            _with_site(limit=3, url_template="https://id.jobstreet.com/{nope}"), None
        )


def test_validate_job_settings_refuses_unknown_keys():
    with pytest.raises(ConfigError, match="not a job setting: output_dir"):
        validate_job_settings({**SETTINGS, "output_dir": "elsewhere"})


@pytest.fixture
def warnings(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    logger = MagicMock()
    monkeypatch.setattr(config_loader, "get_scraper_logger", lambda: logger)
    return logger.warning


@pytest.mark.parametrize("raw", [None, "", "  "])
def test_concurrency_defaults_when_unset(
    raw: str | None, monkeypatch: pytest.MonkeyPatch, warnings: MagicMock
):
    if raw is None:
        monkeypatch.delenv(CONCURRENCY_ENV_VAR, raising=False)
    else:
        monkeypatch.setenv(CONCURRENCY_ENV_VAR, raw)

    assert read_concurrency_from_env() == DEFAULT_CONCURRENCY == 2
    warnings.assert_not_called()


@pytest.mark.parametrize(("raw", "expected"), [("1", 1), ("4", 4), (" 10 ", 10)])
def test_concurrency_reads_the_env_var(
    raw: str, expected: int, monkeypatch: pytest.MonkeyPatch, warnings: MagicMock
):
    monkeypatch.setenv(CONCURRENCY_ENV_VAR, raw)

    assert read_concurrency_from_env() == expected
    warnings.assert_not_called()


@pytest.mark.parametrize("raw", ["0", "11", "-1", "2.5", "abc", "²", "٣", "1e1"])
def test_bad_concurrency_warns_and_uses_the_default(
    raw: str, monkeypatch: pytest.MonkeyPatch, warnings: MagicMock
):
    monkeypatch.setenv(CONCURRENCY_ENV_VAR, raw)

    assert read_concurrency_from_env() == DEFAULT_CONCURRENCY
    warnings.assert_called_once()
    assert CONCURRENCY_ENV_VAR in warnings.call_args.args[0] % warnings.call_args.args[1:]


def test_read_proxy_url_from_env_rejects_unset(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(PROXY_ENV_VAR, raising=False)

    with pytest.raises(ConfigError, match=PROXY_ENV_VAR):
        read_proxy_url_from_env()


def test_read_proxy_url_from_env_treats_empty_as_direct(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(PROXY_ENV_VAR, "  ")

    assert read_proxy_url_from_env() is None


def test_read_proxy_url_from_env_returns_value(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(PROXY_ENV_VAR, " socks5://localhost:1080 ")

    assert read_proxy_url_from_env() == "socks5://localhost:1080"


def test_validate_job_settings_accepts_valid_settings():
    validate_job_settings(SETTINGS)


def test_validate_job_settings_rejects_machine_keys():
    with pytest.raises(ConfigError, match="not a job setting: proxy"):
        validate_job_settings({**SETTINGS, "proxy": "socks5://localhost:1080"})


def test_validate_job_settings_rejects_bad_values():
    with pytest.raises(ConfigError, match="sites.jobstreet.limit"):
        validate_job_settings(_with_site(limit=0))


def test_missing_fields_use_the_built_in_defaults():
    fields = parse_job_settings_into_app_config(SETTINGS, None).list_saved_fields()

    assert fields == {"site", "matched_keyword", "title", "company", "url", "location"}


def test_empty_fields_keep_only_the_always_saved_fields():
    fields = parse_job_settings_into_app_config(
        {**SETTINGS, "fields": []}, None
    ).list_saved_fields()

    assert fields == {"site", "matched_keyword", "title", "company", "url"}


def test_fields_with_only_unknown_names_use_the_built_in_defaults():
    fields = parse_job_settings_into_app_config(
        {**SETTINGS, "fields": ["old_field"]}, None
    ).list_saved_fields()

    assert "location" in fields


def test_known_fields_are_saved_with_the_mandatory_fields():
    fields = parse_job_settings_into_app_config(
        {**SETTINGS, "fields": ["salary", "old_field"]}, None
    ).list_saved_fields()

    assert fields == {"site", "matched_keyword", "title", "company", "url", "salary"}


def test_site_fields_are_refused():
    with pytest.raises(ConfigError, match="sites.jobstreet.fields is no longer supported"):
        validate_job_settings(_with_site(limit=3, fields=["title"]))


def test_default_fields_is_not_a_job_setting():
    with pytest.raises(ConfigError, match="not a job setting: default_fields"):
        validate_job_settings({**SETTINGS, "default_fields": ["title"]})


FILTER_LOCATION_PATH = "sites.jobstreet.filter.location"


def test_location_filter_keeps_the_known_options_in_lowercase():
    site = parse_job_settings_into_app_config(
        _with_site(limit=3, filter={"location": ["Jakarta", " TANGERANG selatan ", "Indonesia"]}),
        None,
    ).find_site_config("jobstreet")

    assert site is not None
    assert site.filter == {"location": ["jakarta", "tangerang selatan", "indonesia"]}


def test_location_filter_given_as_one_text_is_kept_when_known():
    site = parse_job_settings_into_app_config(
        _with_site(limit=3, filter={"location": "Bekasi"}), None
    ).find_site_config("jobstreet")

    assert site is not None
    assert site.filter == {"location": ["bekasi"]}


def test_stored_unknown_location_filter_value_is_dropped_with_a_warning(warnings: MagicMock):
    site = parse_job_settings_into_app_config(
        _with_site(limit=3, filter={"location": ["jakarta", "Surabaya"]}), None
    ).find_site_config("jobstreet")

    assert site is not None
    assert site.filter == {"location": ["jakarta"]}
    warnings.assert_called_once()
    warning_text = warnings.call_args.args[0] % warnings.call_args.args[1:]
    assert FILTER_LOCATION_PATH in warning_text
    assert "surabaya" in warning_text
    assert "Tangerang Selatan" in warning_text


def test_location_filter_with_only_unknown_values_becomes_no_location_filter(
    warnings: MagicMock,
):
    site = parse_job_settings_into_app_config(
        _with_site(limit=3, filter={"location": ["Surabaya"], "work_type": ["remote"]}), None
    ).find_site_config("jobstreet")

    assert site is not None
    assert site.filter == {"work_type": ["remote"]}
    warnings.assert_called_once()


def test_other_filter_fields_keep_any_value(warnings: MagicMock):
    site = parse_job_settings_into_app_config(
        _with_site(limit=3, filter={"work_type": ["Surabaya"]}), None
    ).find_site_config("jobstreet")

    assert site is not None
    assert site.filter == {"work_type": ["surabaya"]}
    warnings.assert_not_called()


@pytest.mark.parametrize("location_filter", [["jakarta", "Surabaya"], "Surabaya"])
def test_refuse_unknown_filter_locations_names_the_value_and_the_allowed_options(
    location_filter: object, warnings: MagicMock
):
    with pytest.raises(ConfigError) as raised:
        refuse_unknown_filter_locations(_with_site(limit=3, filter={"location": location_filter}))

    message = str(raised.value)
    assert FILTER_LOCATION_PATH in message
    assert "Surabaya" in message
    assert "Jakarta, Tangerang, Tangerang Selatan, Bandung, Bekasi, Indonesia" in message
    warnings.assert_not_called()


def test_refuse_unknown_filter_locations_accepts_known_values_in_any_case():
    refuse_unknown_filter_locations(
        _with_site(limit=3, filter={"location": ["JAKARTA", "tangerang selatan", "Indonesia"]})
    )


@pytest.mark.parametrize("empty_location_filter", [None, "", []])
def test_refuse_unknown_filter_locations_accepts_an_empty_location_filter(
    empty_location_filter: object,
):
    refuse_unknown_filter_locations(_with_site(limit=3, filter={"location": empty_location_filter}))


@pytest.mark.parametrize(
    "patch_without_location_filter",
    [
        {},
        {"fields": ["title"]},
        {"sites": {"jobstreet": {"limit": 9}}},
        {"sites": {"jobstreet": {"filter": None}}},
        {"sites": {"jobstreet": {"filter": {"work_type": ["Surabaya"]}}}},
    ],
)
def test_refuse_unknown_filter_locations_accepts_a_patch_without_a_location_filter(
    patch_without_location_filter: dict,
):
    refuse_unknown_filter_locations(patch_without_location_filter)


def test_validate_job_settings_accepts_an_unknown_stored_location_filter_value(
    warnings: MagicMock,
):
    validate_job_settings(_with_site(limit=3, filter={"location": ["jakarta", "depok"]}))

    warnings.assert_called_once()


def test_validate_job_settings_still_reports_non_text_location_filter_values():
    with pytest.raises(ConfigError, match="entries must be strings"):
        validate_job_settings(_with_site(limit=3, filter={"location": ["jakarta", 7]}))
