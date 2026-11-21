from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, urlparse

from .log import get_scraper_logger
from .types import CANONICAL_FIELDS, MANDATORY_FIELDS

DEFAULT_FIELDS: tuple[str, ...] = ("title", "company", "location", "url")

FILTERABLE_FIELDS: frozenset[str] = frozenset({"location", "employment_type", "work_type"})

ALLOWED_URL_HOSTS: frozenset[str] = frozenset(
    {
        "id.jobstreet.com",
        "jobstreet.com",
        "glints.com",
        "id.glints.com",
        "www.linkedin.com",
        "linkedin.com",
        "id.linkedin.com",
        "id.indeed.com",
        "indeed.com",
        "www.indeed.com",
        "www.upwork.com",
    }
)

PROXY_ENV_VAR = "PROXY_URL"

CONCURRENCY_ENV_VAR = "SCRAPER_CONCURRENCY"

DEFAULT_CONCURRENCY = 2

MAX_CONCURRENCY = 10

MAX_SITE_LIMIT = 200

JOB_SETTINGS_KEYS: frozenset[str] = frozenset({"fields", "sites"})

SAMPLE_KEYWORD = "data analyst"


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class ProxyConfig:
    url: str


@dataclass(frozen=True)
class ApiConfig:
    enabled: bool
    locations: tuple[str, ...]
    country_wide: bool
    # (min, max) jittered pause between this site's API calls; None = client default
    delay_seconds: tuple[float, float] | None = None


@dataclass(frozen=True)
class SiteConfig:
    name: str
    enabled: bool
    url_template: str
    limit: int
    max_age_hours: int | None = None
    filter: dict[str, list[str]] = field(default_factory=dict)
    api: ApiConfig | None = None

    def build_search_url_for_keyword(self, keyword: str) -> str:
        return _format_url_template(
            self.name, self.url_template, _build_url_template_values(keyword)
        )


@dataclass(frozen=True)
class AppConfig:
    fields: tuple[str, ...]
    sites: tuple[SiteConfig, ...]
    proxy: ProxyConfig | None = None

    def find_site_config(self, site_name: str) -> SiteConfig | None:
        for site in self.sites:
            if site.name == site_name:
                return site
        return None

    def list_enabled_site_names(self) -> tuple[str, ...]:
        enabled_site_names: list[str] = []
        for site in self.sites:
            if site.enabled:
                enabled_site_names.append(site.name)
        return tuple(enabled_site_names)

    def list_saved_fields(self) -> frozenset[str]:
        return MANDATORY_FIELDS | frozenset(self.fields)


def is_valid_max_age(max_age_hours: object) -> bool:
    try:
        _parse_max_age_hours(max_age_hours, "max_age_hours")
    except ConfigError:
        return False
    return True


def read_proxy_url_from_env() -> str | None:
    proxy_url = os.environ.get(PROXY_ENV_VAR)
    if proxy_url is None:
        raise ConfigError(
            f"{PROXY_ENV_VAR} is not set. "
            "Set it to a proxy URL, or to empty for a direct connection"
        )
    stripped_proxy_url = proxy_url.strip()
    if not stripped_proxy_url:
        return None
    return stripped_proxy_url


def read_concurrency_from_env() -> int:
    concurrency_text = os.environ.get(CONCURRENCY_ENV_VAR, "")
    if not concurrency_text.strip():
        return DEFAULT_CONCURRENCY
    concurrency = _parse_concurrency(concurrency_text)
    if concurrency is not None:
        return concurrency
    get_scraper_logger().warning(
        "[config] %s must be a whole number from 1 to %d, got %r; using %d",
        CONCURRENCY_ENV_VAR,
        MAX_CONCURRENCY,
        concurrency_text,
        DEFAULT_CONCURRENCY,
    )
    return DEFAULT_CONCURRENCY


def validate_job_settings(settings: dict[str, Any]) -> None:
    unknown = sorted(set(settings) - JOB_SETTINGS_KEYS)
    if unknown:
        raise ConfigError(f"not a job setting: {', '.join(unknown)}")
    parse_job_settings_into_app_config(settings, None)


def parse_job_settings_into_app_config(
    job_settings: dict[str, Any], proxy_url: str | None
) -> AppConfig:
    sites_raw = job_settings.get("sites")
    if not isinstance(sites_raw, dict) or not sites_raw:
        raise ConfigError("config must define a non-empty 'sites' mapping")

    fields = _parse_saved_fields(job_settings)
    sample_template_values = _build_url_template_values(SAMPLE_KEYWORD)
    sites = tuple(
        _parse_site_config(site_name, site_settings, sample_template_values)
        for site_name, site_settings in sites_raw.items()
    )

    proxy: ProxyConfig | None = None
    if proxy_url and proxy_url.strip():
        proxy = ProxyConfig(url=proxy_url.strip())

    return AppConfig(
        fields=fields,
        sites=sites,
        proxy=proxy,
    )


def build_keyword_slug(keyword: str) -> str:
    keyword_slug = keyword.strip().replace("/", "-").replace("\\", "-")
    while ".." in keyword_slug:
        keyword_slug = keyword_slug.replace("..", ".")
    return keyword_slug.lower().replace(" ", "-")


def _parse_saved_fields(job_settings: dict[str, Any]) -> tuple[str, ...]:
    if "fields" not in job_settings:
        return DEFAULT_FIELDS
    raw_fields = job_settings["fields"]
    known_fields = _keep_known_field_names(raw_fields, "fields")
    if known_fields:
        return known_fields
    if raw_fields:
        return DEFAULT_FIELDS
    return ()


def _validate_url_template_scheme_and_host(site_name: str, url_template: str) -> None:
    parsed = urlparse(url_template)
    if parsed.scheme not in ("http", "https"):
        raise ConfigError(
            f"site '{site_name}' url_template scheme must be http or https, got '{parsed.scheme}'"
        )
    host = (parsed.hostname or "").lower()
    if "{" in host or "}" in host:
        raise ConfigError(
            f"site '{site_name}' url_template hostname must be a fixed domain, not a placeholder"
        )
    if host not in ALLOWED_URL_HOSTS:
        raise ConfigError(
            f"site '{site_name}' url_template has disallowed host '{host}'; "
            f"allowed: {sorted(ALLOWED_URL_HOSTS)}"
        )


def _build_url_template_values(keyword: str) -> dict[str, str]:
    stripped = keyword.strip()
    return {
        "keyword": quote(stripped),
        "keyword_slug": build_keyword_slug(stripped),
        "keyword_plus": stripped.replace(" ", "+"),
    }


def _format_url_template(site_name: str, url_template: str, template_values: dict[str, str]) -> str:
    try:
        return url_template.format(**template_values)
    except KeyError as exc:
        raise ConfigError(
            f"site '{site_name}' url_template uses unknown placeholder {exc}; "
            f"allowed: {sorted(template_values)}"
        ) from exc


def _parse_max_age_hours(max_age_hours: object, setting_path: str) -> int | None:
    if max_age_hours is None:
        return None
    if isinstance(max_age_hours, bool) or not isinstance(max_age_hours, int | float | str):
        raise ConfigError(
            f"{setting_path} must be a positive integer or null, got {max_age_hours!r}"
        )
    try:
        parsed_max_age_hours = int(max_age_hours)
    except (TypeError, ValueError) as exc:
        raise ConfigError(
            f"{setting_path} must be a positive integer or null, got {max_age_hours!r}"
        ) from exc
    if parsed_max_age_hours < 1:
        raise ConfigError(f"{setting_path} must be >= 1, got {parsed_max_age_hours}")
    return parsed_max_age_hours


def _parse_site_limit(site_settings: dict[str, Any], site_name: str) -> int:
    setting_path = f"sites.{site_name}.limit"
    if "limit" not in site_settings:
        raise ConfigError(f"{setting_path} is required")
    site_limit = site_settings["limit"]
    is_whole = isinstance(site_limit, int) and not isinstance(site_limit, bool)
    if not is_whole or not 1 <= site_limit <= MAX_SITE_LIMIT:
        raise ConfigError(
            f"{setting_path} must be a whole number from 1 to {MAX_SITE_LIMIT}, got {site_limit!r}"
        )
    return site_limit


def _keep_known_field_names(field_names: object, setting_path: str) -> tuple[str, ...]:
    if not isinstance(field_names, list):
        raise ConfigError(
            f"{setting_path} must be a list of field names, got {type(field_names).__name__}"
        )

    known_field_names: list[str] = []
    for field_name in field_names:
        if not isinstance(field_name, str):
            raise ConfigError(f"{setting_path} entries must be strings, got {field_name!r}")
        if field_name not in CANONICAL_FIELDS:
            get_scraper_logger().warning(
                "[config] %s contains unknown field '%s'; ignored. allowed: %s",
                setting_path,
                field_name,
                sorted(CANONICAL_FIELDS),
            )
            continue
        known_field_names.append(field_name)
    return tuple(known_field_names)


def _convert_filter_value_to_lowercase_list(filter_value: object, setting_path: str) -> list[str]:
    if isinstance(filter_value, str):
        lowercase_filter_text = filter_value.strip().lower()
        if not lowercase_filter_text:
            return []
        return [lowercase_filter_text]
    if isinstance(filter_value, list):
        lowercase_filter_texts: list[str] = []
        for filter_text in filter_value:
            if not isinstance(filter_text, str):
                raise ConfigError(f"{setting_path} entries must be strings, got {filter_text!r}")
            lowercase_filter_text = filter_text.strip().lower()
            if lowercase_filter_text:
                lowercase_filter_texts.append(lowercase_filter_text)
        return lowercase_filter_texts
    raise ConfigError(
        f"{setting_path} must be a string or list of strings, got {type(filter_value).__name__}"
    )


def _keep_known_filter_fields(site_filter: object, setting_path: str) -> dict[str, list[str]]:
    if site_filter is None:
        return {}
    if not isinstance(site_filter, dict):
        raise ConfigError(f"{setting_path} must be a mapping, got {type(site_filter).__name__}")
    known_filters: dict[str, list[str]] = {}
    for filter_field, filter_value in site_filter.items():
        if not isinstance(filter_field, str):
            raise ConfigError(f"{setting_path} keys must be strings, got {filter_field!r}")
        if filter_field not in FILTERABLE_FIELDS:
            get_scraper_logger().warning(
                "[config] %s contains unknown filter field '%s'; ignored. allowed: %s",
                setting_path,
                filter_field,
                sorted(FILTERABLE_FIELDS),
            )
            continue
        if filter_value is None or filter_value == "":
            continue
        lowercase_filter_texts = _convert_filter_value_to_lowercase_list(
            filter_value, f"{setting_path}.{filter_field}"
        )
        if lowercase_filter_texts:
            known_filters[filter_field] = lowercase_filter_texts
    return known_filters


def _parse_api_config(api_settings: object, setting_path: str) -> ApiConfig | None:
    if api_settings is None:
        return None
    if not isinstance(api_settings, dict):
        raise ConfigError(f"{setting_path} must be a mapping")
    return ApiConfig(
        enabled=bool(api_settings.get("enabled", True)),
        locations=_strip_api_locations(
            api_settings.get("locations", []), f"{setting_path}.locations"
        ),
        country_wide=bool(api_settings.get("country_wide", False)),
        delay_seconds=_parse_delay_seconds_range(
            api_settings.get("delay_seconds"), f"{setting_path}.delay_seconds"
        ),
    )


def _strip_api_locations(locations_setting: object, setting_path: str) -> tuple[str, ...]:
    if not isinstance(locations_setting, list):
        raise ConfigError(f"{setting_path} must be a list of non-empty strings")
    stripped_locations: list[str] = []
    for location in locations_setting:
        if not isinstance(location, str):
            raise ConfigError(f"{setting_path} must be a list of non-empty strings")
        stripped_location = location.strip()
        if not stripped_location:
            raise ConfigError(f"{setting_path} must be a list of non-empty strings")
        stripped_locations.append(stripped_location)
    return tuple(stripped_locations)


def _parse_delay_seconds_range(
    delay_seconds: object, setting_path: str
) -> tuple[float, float] | None:
    if delay_seconds is None:
        return None
    invalid_delay_range_error = ConfigError(
        f"{setting_path} must be [min, max] seconds with 0 <= min <= max"
    )
    if not isinstance(delay_seconds, list) or len(delay_seconds) != 2:
        raise invalid_delay_range_error
    try:
        low, high = float(delay_seconds[0]), float(delay_seconds[1])
    except (TypeError, ValueError) as exc:
        raise invalid_delay_range_error from exc
    if not 0 <= low <= high:
        raise invalid_delay_range_error
    return (low, high)


def _parse_concurrency(concurrency_text: str) -> int | None:
    stripped_concurrency_text = concurrency_text.strip()
    if not stripped_concurrency_text.isascii() or not stripped_concurrency_text.isdigit():
        return None
    try:
        concurrency = int(stripped_concurrency_text)
    except ValueError:
        return None
    if not 1 <= concurrency <= MAX_CONCURRENCY:
        return None
    return concurrency


def _parse_site_config(
    site_name: str, site_settings: object, sample_template_values: dict[str, str]
) -> SiteConfig:
    if not isinstance(site_settings, dict):
        raise ConfigError(f"site '{site_name}' must be a mapping")
    url_template = site_settings.get("url_template")
    if not isinstance(url_template, str) or not url_template:
        raise ConfigError(f"site '{site_name}' must define non-empty 'url_template'")
    _validate_url_template_scheme_and_host(site_name, url_template)
    _format_url_template(site_name, url_template, sample_template_values)
    _refuse_site_fields(site_name, site_settings)
    return SiteConfig(
        name=site_name,
        enabled=bool(site_settings.get("enabled", True)),
        url_template=url_template,
        limit=_parse_site_limit(site_settings, site_name),
        max_age_hours=_parse_max_age_hours(
            site_settings.get("max_age_hours"), f"sites.{site_name}.max_age_hours"
        ),
        filter=_keep_known_filter_fields(site_settings.get("filter"), f"sites.{site_name}.filter"),
        api=_parse_api_config(site_settings.get("api"), f"sites.{site_name}.api"),
    )


def _refuse_site_fields(site_name: str, site_settings: dict[str, Any]) -> None:
    if "fields" not in site_settings:
        return
    raise ConfigError(f"sites.{site_name}.fields is no longer supported, use the top-level fields")
