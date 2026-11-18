from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, urlparse

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

JOB_SETTINGS_KEYS: frozenset[str] = frozenset({"default_fields", "sites"})

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
    fields: tuple[str, ...] | None = None
    max_age_hours: int | None = None
    filter: dict[str, list[str]] = field(default_factory=dict)
    api: ApiConfig | None = None

    def effective_fields(self, default: tuple[str, ...]) -> tuple[str, ...]:
        return self.fields if self.fields is not None else default

    def url_for(self, keyword: str) -> str:
        return _resolve_url(self.name, self.url_template, _build_template_vars(keyword))


@dataclass(frozen=True)
class AppConfig:
    default_fields: tuple[str, ...]
    sites: tuple[SiteConfig, ...]
    proxy: ProxyConfig | None = None

    def site(self, name: str) -> SiteConfig | None:
        for site in self.sites:
            if site.name == name:
                return site
        return None

    def enabled_site_names(self) -> tuple[str, ...]:
        return tuple(site.name for site in self.sites if site.enabled)

    def fields_for(self, site_name: str) -> frozenset[str]:
        cfg = self.site(site_name)
        configured = (
            cfg.effective_fields(self.default_fields) if cfg is not None else self.default_fields
        )
        return MANDATORY_FIELDS | frozenset(configured)


def _slugify(keyword: str) -> str:
    safe = keyword.strip().replace("/", "-").replace("\\", "-")
    while ".." in safe:
        safe = safe.replace("..", ".")
    return safe.lower().replace(" ", "-")


def _validate_url_host(site_name: str, template: str) -> None:
    parsed = urlparse(template)
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


def _build_template_vars(keyword: str) -> dict[str, str]:
    stripped = keyword.strip()
    return {
        "keyword": quote(stripped),
        "keyword_slug": _slugify(stripped),
        "keyword_plus": stripped.replace(" ", "+"),
    }


def _resolve_url(site_name: str, template: str, vars_: dict[str, str]) -> str:
    try:
        return template.format(**vars_)
    except KeyError as exc:
        raise ConfigError(
            f"site '{site_name}' url_template uses unknown placeholder {exc}; "
            f"allowed: {sorted(vars_)}"
        ) from exc


def _parse_max_age(raw: object, source: str) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int | float | str):
        raise ConfigError(f"{source} must be a positive integer or null, got {raw!r}")
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{source} must be a positive integer or null, got {raw!r}") from exc
    if value < 1:
        raise ConfigError(f"{source} must be >= 1, got {value}")
    return value


def is_valid_max_age(raw: object) -> bool:
    try:
        _parse_max_age(raw, "max_age_hours")
    except ConfigError:
        return False
    return True


def _parse_site_limit(cfg: dict[str, Any], name: str) -> int:
    source = f"sites.{name}.limit"
    if "limit" not in cfg:
        raise ConfigError(f"{source} is required")
    value = cfg["limit"]
    is_whole = isinstance(value, int) and not isinstance(value, bool)
    if not is_whole or not 1 <= value <= MAX_SITE_LIMIT:
        raise ConfigError(
            f"{source} must be a whole number from 1 to {MAX_SITE_LIMIT}, got {value!r}"
        )
    return value


def _validate_fields(raw: object, source: str) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise ConfigError(f"{source} must be a list of field names, got {type(raw).__name__}")

    cleaned: list[str] = []
    for entry in raw:
        if not isinstance(entry, str):
            raise ConfigError(f"{source} entries must be strings, got {entry!r}")
        if entry not in CANONICAL_FIELDS:
            from .log import get_logger as _get_logger

            _get_logger().warning(
                "[config] %s contains unknown field '%s'; ignored. allowed: %s",
                source,
                entry,
                sorted(CANONICAL_FIELDS),
            )
            continue
        cleaned.append(entry)
    return tuple(cleaned)


def _normalize_filter_value(raw: object, source: str) -> list[str]:
    if isinstance(raw, str):
        normalized = raw.strip().lower()
        return [normalized] if normalized else []
    if isinstance(raw, list):
        cleaned: list[str] = []
        for entry in raw:
            if not isinstance(entry, str):
                raise ConfigError(f"{source} entries must be strings, got {entry!r}")
            normalized = entry.strip().lower()
            if normalized:
                cleaned.append(normalized)
        return cleaned
    raise ConfigError(f"{source} must be a string or list of strings, got {type(raw).__name__}")


def _validate_filter(raw: object, source: str) -> dict[str, list[str]]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigError(f"{source} must be a mapping, got {type(raw).__name__}")
    cleaned: dict[str, list[str]] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            raise ConfigError(f"{source} keys must be strings, got {key!r}")
        if key not in FILTERABLE_FIELDS:
            from .log import get_logger as _get_logger

            _get_logger().warning(
                "[config] %s contains unknown filter field '%s'; ignored. allowed: %s",
                source,
                key,
                sorted(FILTERABLE_FIELDS),
            )
            continue
        if value is None or value == "":
            continue
        items = _normalize_filter_value(value, f"{source}.{key}")
        if items:
            cleaned[key] = items
    return cleaned


def _parse_api(raw: object, source: str) -> ApiConfig | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ConfigError(f"{source} must be a mapping")
    locations_raw = raw.get("locations", [])
    if not isinstance(locations_raw, list) or not all(
        isinstance(item, str) and item.strip() for item in locations_raw
    ):
        raise ConfigError(f"{source}.locations must be a list of non-empty strings")
    return ApiConfig(
        enabled=bool(raw.get("enabled", True)),
        locations=tuple(item.strip() for item in locations_raw),
        country_wide=bool(raw.get("country_wide", False)),
        delay_seconds=_parse_delay(raw.get("delay_seconds"), f"{source}.delay_seconds"),
    )


def _parse_delay(raw: object, source: str) -> tuple[float, float] | None:
    if raw is None:
        return None
    error = ConfigError(f"{source} must be [min, max] seconds with 0 <= min <= max")
    if not isinstance(raw, list) or len(raw) != 2:
        raise error
    try:
        low, high = float(raw[0]), float(raw[1])
    except (TypeError, ValueError) as exc:
        raise error from exc
    if not 0 <= low <= high:
        raise error
    return (low, high)


def resolve_proxy_url() -> str | None:
    value = os.environ.get(PROXY_ENV_VAR)
    if value is None:
        raise ConfigError(
            f"{PROXY_ENV_VAR} is not set. "
            "Set it to a proxy URL, or to empty for a direct connection"
        )
    return value.strip() or None


def _parse_concurrency(raw: str) -> int | None:
    value = raw.strip()
    if not value.isascii() or not value.isdigit():
        return None
    try:
        number = int(value)
    except ValueError:
        return None
    return number if 1 <= number <= MAX_CONCURRENCY else None


def resolve_concurrency() -> int:
    raw = os.environ.get(CONCURRENCY_ENV_VAR, "")
    if not raw.strip():
        return DEFAULT_CONCURRENCY
    value = _parse_concurrency(raw)
    if value is not None:
        return value
    from .log import get_logger as _get_logger

    _get_logger().warning(
        "[config] %s must be a whole number from 1 to %d, got %r; using %d",
        CONCURRENCY_ENV_VAR,
        MAX_CONCURRENCY,
        raw,
        DEFAULT_CONCURRENCY,
    )
    return DEFAULT_CONCURRENCY


def validate_job_settings(settings: dict[str, Any]) -> None:
    unknown = sorted(set(settings) - JOB_SETTINGS_KEYS)
    if unknown:
        raise ConfigError(f"not a job setting: {', '.join(unknown)}")
    parse(settings, None)


def _parse_site(name: str, cfg: object, sample_vars: dict[str, str]) -> SiteConfig:
    if not isinstance(cfg, dict):
        raise ConfigError(f"site '{name}' must be a mapping")
    template = cfg.get("url_template")
    if not isinstance(template, str) or not template:
        raise ConfigError(f"site '{name}' must define non-empty 'url_template'")
    _validate_url_host(name, template)
    _resolve_url(name, template, sample_vars)
    fields = _validate_fields(cfg["fields"], f"sites.{name}.fields") if "fields" in cfg else None
    return SiteConfig(
        name=name,
        enabled=bool(cfg.get("enabled", True)),
        url_template=template,
        limit=_parse_site_limit(cfg, name),
        fields=fields,
        max_age_hours=_parse_max_age(cfg.get("max_age_hours"), f"sites.{name}.max_age_hours"),
        filter=_validate_filter(cfg.get("filter"), f"sites.{name}.filter"),
        api=_parse_api(cfg.get("api"), f"sites.{name}.api"),
    )


def parse(raw: dict[str, Any], proxy_url: str | None) -> AppConfig:
    sites_raw = raw.get("sites")
    if not isinstance(sites_raw, dict) or not sites_raw:
        raise ConfigError("config must define a non-empty 'sites' mapping")

    if "default_fields" in raw:
        default_fields = _validate_fields(raw["default_fields"], "default_fields")
        # An empty list is a choice: keep only the always-saved fields. A list
        # whose names were all unknown falls back to the defaults instead
        if not default_fields and raw["default_fields"]:
            default_fields = DEFAULT_FIELDS
    else:
        default_fields = DEFAULT_FIELDS

    sample_vars = _build_template_vars(SAMPLE_KEYWORD)
    sites = tuple(_parse_site(name, cfg, sample_vars) for name, cfg in sites_raw.items())

    proxy: ProxyConfig | None = None
    if proxy_url and proxy_url.strip():
        proxy = ProxyConfig(url=proxy_url.strip())

    return AppConfig(
        default_fields=default_fields,
        sites=sites,
        proxy=proxy,
    )


def keyword_slug(keyword: str) -> str:
    return _slugify(keyword)
