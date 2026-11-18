from __future__ import annotations

import pytest

from scraper.config_loader import (
    DEFAULT_CONCURRENCY,
    PROXY_ENV_VAR,
    ConfigError,
    parse,
    resolve_proxy_url,
    validate_job_settings,
)

SETTINGS = {
    "keywords": ["devops"],
    "limit": 3,
    "sites": {"jobstreet": {"url_template": "https://id.jobstreet.com/id/{keyword_slug}-jobs"}},
}


def test_parse_builds_config_with_proxy():
    config = parse({**SETTINGS, "concurrency": 4}, "socks5://localhost:1080")

    assert config.keywords == ("devops",)
    assert config.concurrency == 4
    assert config.proxy is not None
    assert config.proxy.url == "socks5://localhost:1080"


def test_parse_without_proxy():
    assert parse(SETTINGS, None).proxy is None


def test_parse_uses_default_concurrency_and_has_no_output_dir():
    config = parse(SETTINGS, None)

    assert config.concurrency == DEFAULT_CONCURRENCY
    assert not hasattr(config, "output_dir")


def test_validate_job_settings_accepts_concurrency():
    validate_job_settings({**SETTINGS, "concurrency": 3})


@pytest.mark.parametrize("value", [0, 11, 2.7, "3", True])
def test_parse_refuses_bad_concurrency(value: object):
    with pytest.raises(ConfigError, match="'concurrency' must be a whole number from 1 to 10"):
        parse({**SETTINGS, "concurrency": value}, None)


def test_parse_uses_default_concurrency_for_a_stored_null():
    assert parse({**SETTINGS, "concurrency": None}, None).concurrency == DEFAULT_CONCURRENCY


def test_validate_job_settings_refuses_unknown_keys():
    with pytest.raises(ConfigError, match="not a job setting: output_dir"):
        validate_job_settings({**SETTINGS, "output_dir": "elsewhere"})


def test_resolve_proxy_url_rejects_unset(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(PROXY_ENV_VAR, raising=False)

    with pytest.raises(ConfigError, match=PROXY_ENV_VAR):
        resolve_proxy_url()


def test_resolve_proxy_url_treats_empty_as_direct(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(PROXY_ENV_VAR, "  ")

    assert resolve_proxy_url() is None


def test_resolve_proxy_url_returns_value(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(PROXY_ENV_VAR, " socks5://localhost:1080 ")

    assert resolve_proxy_url() == "socks5://localhost:1080"


def test_validate_job_settings_accepts_valid_settings():
    validate_job_settings(SETTINGS)


def test_validate_job_settings_rejects_machine_keys():
    with pytest.raises(ConfigError, match="not a job setting: proxy"):
        validate_job_settings({**SETTINGS, "proxy": "socks5://localhost:1080"})


def test_validate_job_settings_rejects_bad_values():
    with pytest.raises(ConfigError, match="'limit' must be >= 1"):
        validate_job_settings({**SETTINGS, "limit": 0})


def test_missing_default_fields_use_the_built_in_defaults():
    fields = parse(SETTINGS, None).fields_for("jobstreet")

    assert fields == {"site", "matched_keyword", "title", "company", "url", "location"}


def test_empty_default_fields_keep_only_the_always_saved_fields():
    fields = parse({**SETTINGS, "default_fields": []}, None).fields_for("jobstreet")

    assert fields == {"site", "matched_keyword", "title", "company", "url"}


def test_default_fields_with_only_unknown_names_use_the_built_in_defaults():
    fields = parse({**SETTINGS, "default_fields": ["old_field"]}, None).fields_for("jobstreet")

    assert "location" in fields
