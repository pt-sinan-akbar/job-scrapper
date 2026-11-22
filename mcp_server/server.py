from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import product
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from mcp.server.fastmcp import FastMCP  # type: ignore[import-untyped]
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from mcp_server import mongo
from mcp_server.discord_tools import DISCORD_TOOLS
from scraper.api.location_search_plan import (
    build_unknown_location_message,
    find_filter_location_option,
    list_filter_location_options,
)
from scraper.config import ACCEPT_LANGUAGE, USER_AGENT
from scraper.config_loader import SAMPLE_KEYWORD, AppConfig, ConfigError
from scraper.job_settings import (
    JobSettingsStore,
    SettingsConflictError,
    SettingsMissingError,
    SettingsUnavailableError,
    StoredSettings,
    load_app_config,
)
from scraper.log import get_scraper_logger as _get_scraper_logger
from scraper.log import hide_proxy_password as _hide_proxy_password
from scraper.max_age import build_unknown_max_age_message, is_max_age_option, list_max_age_options
from scraper.runner import (
    KEYWORDS_REQUIRED,
    RunResult,
    scrape_all_sites,
    strip_and_drop_blank_keywords,
)
from scraper.types import JOB_FIELD_ORDER, MANDATORY_FIELDS

DEFAULT_PROXY_TEST_URL = os.environ.get(
    "PROXY_TEST_URL",
    "https://api.ipify.org?format=json",
)
PROXY_TEST_TIMEOUT_SEC = float(os.environ.get("PROXY_TEST_TIMEOUT_SEC", "25"))
CHROME_IMPERSONATE = "chrome131"
HOST = os.environ.get("MCP_HOST", "0.0.0.0")
PORT = int(os.environ.get("MCP_PORT", "8080"))

HTTP_OK = 200
PROBE_EXCERPT_CHARS = 512
PLAIN_IP_MAX_CHARS = 64
MILLISECONDS_PER_SECOND = 1000
ALLOWED_TEST_URL_SCHEMES = ("http", "https")
NO_PROXY_MESSAGE = "no proxy set in PROXY_URL and proxy_url not passed — set it or pass proxy_url"
SAMPLE_MONGO_ID = "665f1c2e9b1d4a0012345678"

_STATUS_PATH = Path("logs/status.json")

mcp = FastMCP("job-scraper", host=HOST, port=PORT)

for discord_tool in DISCORD_TOOLS:
    mcp.tool()(discord_tool)

SaveSource = Literal["ui", "mcp"]


@mcp.custom_route("/health", methods=["GET"])
async def check_health(request: Request) -> Response:
    try:
        await run_in_threadpool(mongo.ping_mongo)
    except Exception as exc:
        _get_scraper_logger().warning("health check: mongo ping failed: %s", exc)
        return JSONResponse({"status": "degraded", "mongo": "error"}, status_code=503)
    return JSONResponse({"status": "ok", "mongo": "ok"})


@mcp.tool()
def list_sites() -> dict[str, Any]:
    """List sites from the job settings with their enabled status.

    Each site shows its raw url_template plus a sample resolved URL formatted
    against the placeholder keyword "data analyst". The job settings hold no
    keywords: every scrape_jobs call names its own.
    """
    try:
        config = _load_app_config()
    except ConfigError as exc:
        return {"error": str(exc)}
    return {"sites": [_build_site_listing_entry(site) for site in config.sites]}


@mcp.tool()
def get_config() -> dict[str, Any]:
    """Return the job settings stored in Mongo, with their version.

    Use this before update_config to see the current shape, then send a
    minimal patch to change only what you want. job_fields lists every field
    name the top-level fields list accepts; mandatory_fields are always
    saved for each job, whatever the settings say. location_options lists the
    values every site's filter.location accepts: the cities first, then
    Indonesia, which means all regions. max_age_options lists the only
    values scrape_jobs accepts as max_age_hours, each as {value, label}.
    """
    try:
        stored_settings = _build_job_settings_store().read()
    except ConfigError as exc:
        return {"error": str(exc)}
    return {
        **_convert_stored_settings_to_dict(stored_settings),
        "job_fields": list(JOB_FIELD_ORDER),
        "mandatory_fields": _list_mandatory_fields(),
        "location_options": list_filter_location_options(),
        "max_age_options": list_max_age_options(),
    }


@mcp.tool()
def get_scrape_response_structure() -> dict[str, Any]:
    """Return canonical schema and example payload for scrape_jobs response."""
    return {
        "tool": "scrape_jobs",
        "version": "2.0.0",
        "job_fields": list(JOB_FIELD_ORDER),
        "top_level_fields": [
            "ok",
            "keywords",
            "requested_sites",
            "exit_code",
            "results",
            "errors",
            "mongo_id",
        ],
        "optional_top_level_fields": ["raw_results"],
        "result_fields": ["keyword", "site", "payload"],
        "payload_fields": [
            "keyword",
            "fields",
            "max_age_hours",
            "filter",
            "count",
            "jobs",
            "source",
            "fallback_reason",
        ],
        "error_fields": ["keyword", "site", "reason", "attempts"],
        "sample": _build_sample_response(),
    }


@mcp.tool()
def update_config(
    patch: dict[str, Any],
    expected_version: int | None = None,
    source: SaveSource = "mcp",
) -> dict[str, Any]:
    """Apply a patch to the job settings after validating the result.

    Top-level keys are fields and sites, each replaced whole. fields is one
    list for every site; a site has no fields of its own.
    Keywords are not a job setting: pass them to scrape_jobs on every call.
    `sites` merges by site name, and each field of a site is replaced whole.
    limit, max_age_hours and filter live only on a site: there are no global
    values. Every site needs a limit (1 to 200). A null value removes that
    key: max_age_hours null means no age cut, and filter {} means no filter.
    Scrape concurrency comes from the SCRAPER_CONCURRENCY env var.

    Args:
        patch: changes to apply. Examples:
            {"fields": ["title", "company", "url", "salary"]}
            {"sites": {"glints": {"limit": 10, "max_age_hours": 24}}}
            {"sites": {"linkedin": {"enabled": false}}}
            {"sites": {"glints": {"max_age_hours": null}}}
            {"sites": {"upwork": {"filter": {}}}}
        expected_version: version you read with get_config. When it is not the
            current version, nothing is saved and reason is "conflict".
        source: who made the change, kept with the version.

    Returns:
        On success: {ok: True, version, updated_at, updated_by, settings}
        On failure: {ok: False, reason, message}. reason is "invalid",
        "conflict", or "unavailable".
    """
    return _save_settings_and_build_response(
        lambda: _build_job_settings_store().save(patch, expected_version, source)
    )


@mcp.tool()
def get_scrape_status() -> dict[str, Any]:
    """Return the status of the last scrape_jobs run.

    Returns:
        dict with keys:
            available: false when no run has been recorded yet
            last_run: {timestamp, ok, duration_seconds, keywords, sites,
                       total_jobs, error_count, errors}
            last_error: last error entry with timestamp, or null if last run clean
            per_site: {site_name: {last_run_at, last_status, last_job_count, last_error}}
    """
    if not _STATUS_PATH.exists():
        return {"available": False, "message": "No scrape run has been recorded yet."}

    try:
        scrape_status = json.loads(_STATUS_PATH.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return {"available": False, "error": f"Could not read status file: {exc}"}

    return {"available": True, **scrape_status}


@mcp.tool()
def insert_scrape_run(run_data: dict[str, Any]) -> dict[str, Any]:
    """Insert a scraping run record into MongoDB for history tracking.

    Args:
        run_data: Arbitrary dict with run details. Recommended keys:
            run_metadata: {ok, exit_code, keywords, requested_sites, errors,
                           per_site_counts, per_site_sources,
                           bot_post_status}
            results: [{keyword, site, payload}], the same list scrape_jobs
                     returns
            note: failure summary string, or null
            channel_id: Discord channel id (never the bot token)
            discord_sent_status: "success" | "failed"
            filtered_results and raw_results are no longer recommended keys:
            scrape_jobs saves the filtered payloads as results and never saves
            raw results.

    Returns:
        On success: {ok: true, inserted_id: <str>}
        On failure: {ok: false, error: <str>}
    """
    try:
        inserted_id = mongo.insert_run(run_data)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "inserted_id": inserted_id}


@mcp.tool()
def get_latest_scrape_run() -> dict[str, Any]:
    """Return the most recent scraping run record from MongoDB.

    Returns:
        {available: false, message: str} when no runs have been recorded
        {available: false, error: str} when MongoDB is unreachable
        {available: true, _id, _created_at, run_metadata, results, note,
         channel_id, discord_sent_status, ...} on success. results is
         [{keyword, site, payload}]. The run is returned as stored: a run saved
         before results replaced filtered_results has filtered_results (the
         same list under the old name) instead of results, and may also carry
         raw_results. Newer runs have neither.
    """
    try:
        latest_run = mongo.read_latest_run()
    except Exception as exc:
        return {"available": False, "error": str(exc)}
    if latest_run is None:
        return {"available": False, "message": "No scrape runs recorded yet."}
    return {"available": True, **latest_run}


@mcp.tool()
def update_scrape_run(run_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    """Patch an existing scrape run document (from scrape_jobs' mongo_id).

    Used by the bot to add Discord columns to the SAME run document instead of
    inserting a second one. Recommended patch keys:
        channel_id: str (Discord channel id — NOT the bot token)
        discord_sent_status: "success" | "failed"
        run_metadata.bot_post_status: {total_posted, failed}  (dot-notation key)

    Returns {ok: true, matched: <bool>} or {ok: false, error: <str>}.
    """
    try:
        matched = mongo.update_run(run_id, patch)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "matched": matched}


@mcp.tool()
def test_proxy_connection(
    proxy_url: str | None = None,
    url: str | None = None,
) -> dict[str, Any]:
    """Check that an HTTP(S) request succeeds through the configured proxy.

    Uses the same curl_cffi transport as the scraper HTML downloaders (HTTP, HTTPS,
    SOCKS5 URLs as supported by curl_cffi).

    Args:
        proxy_url: optional override; when omitted, uses
            ``PROXY_URL``. When no proxy is set and this is omitted, returns
            an error.
        url: optional URL to fetch (default: ``PROXY_TEST_URL`` env or
            https://api.ipify.org?format=json). Must be http or https.

    Returns:
        On success: {ok: true, proxy_redacted, test_url, http_status, duration_ms,
            egress_ip? , response_excerpt?}
        On failure: {ok: false, proxy_redacted?, test_url?, error, ...}
    """
    try:
        test_url = _choose_passed_or_default_test_url(url)
        tested_proxy_url, is_proxy_from_config = _choose_passed_or_config_proxy_url(proxy_url)
    except _ProxyTestError as exc:
        return {"ok": False, "error": str(exc)}

    redacted_proxy_url = _hide_proxy_password(tested_proxy_url)
    _get_scraper_logger().info(
        "test_proxy_connection proxy=%s test_url=%s", redacted_proxy_url, test_url
    )

    started_at = time.monotonic()
    probe_result = _probe_proxy_http(tested_proxy_url, test_url)
    duration_ms = round((time.monotonic() - started_at) * MILLISECONDS_PER_SECOND, 2)

    proxy_test_details: dict[str, Any] = {
        "proxy_redacted": redacted_proxy_url,
        "test_url": test_url,
        "duration_ms": duration_ms,
    }
    if is_proxy_from_config:
        proxy_test_details = {**proxy_test_details, "source": "config"}

    proxy_test_result = {**proxy_test_details, **probe_result}
    _log_proxy_test_result(proxy_test_result)
    return proxy_test_result


@mcp.tool()
def scrape_jobs(
    sites: list[str] | None = None,
    *,
    keywords: list[str] | None,
    save_run: bool = True,
    include_raw_results: bool = False,
    location: str | None = None,
    max_age_hours: int | None = None,
) -> dict[str, Any]:
    """Run the job scraper and return aggregated results.

    Args:
        sites: optional list of site names to scrape. When omitted, runs every
            site marked enabled in the job settings.
        keywords: required list of keywords to scrape, passed by name. The job
            settings hold no keywords, so there is no fallback. Each keyword is
            trimmed and blank ones are dropped. When none are left, nothing
            runs and nothing is saved: the response has ok=false,
            exit_code=1, keywords=[], results=[], mongo_id=null and
            errors=[{keyword: null, site: null, reason: "keywords are required"}].
        save_run: when false, return the results without storing the run in
            Mongo, so it never reaches the scrape history. mongo_id is then null.
            A stored run keeps run_metadata, results and note. raw_results
            is never stored.
        include_raw_results: when true, the response also carries raw_results,
            a list of {keyword, site, payload} with each site's payload before
            max-age, filter and limit. Off by default to keep the response
            small. raw_results exists only in this response.
        location: optional city that each site's API searches for this call
            only, one of get_config's location_options, matched without
            regard to case. Indonesia means a country-wide search only. When
            omitted or null, each site searches the cities of its saved
            filter.location. The saved filter.location still filters the
            results either way, and HTML scraping ignores this argument. An
            unknown value scrapes nothing and saves nothing: the response has
            ok=false, exit_code=1, keywords=[], results=[], mongo_id=null and
            errors=[{keyword: null, site: null, reason: "unknown location:
            <value>. allowed: <options>"}].
        max_age_hours: optional max job age in hours for this call only, one
            of the values in get_config's max_age_options (72, 168 or 720).
            It replaces every site's saved max_age_hours for this call, both
            in the site's search date range and in the stale cut. The stale
            cut keeps jobs posted on or after midnight UTC of today minus the
            hours rounded up to whole days. When omitted or null, each site
            uses its saved max_age_hours. The saved settings never change.
            Any other value scrapes nothing and saves nothing: the response
            has ok=false, exit_code=1, keywords=[], results=[], mongo_id=null
            and errors=[{keyword: null, site: null, reason: "unknown
            max_age_hours: <value>. allowed: 72, 168, 720"}].

    Returns:
        dict with keys:
            ok: true when every requested site was reached, regardless of job
                count. Zero jobs with ok=true means the site responded but
                nothing matched your filters or date range — this is normal,
                not an error. ok=false means at least one site failed to fetch.
            keywords: list of keywords actually attempted
            requested_sites: list of site names attempted (per keyword)
            exit_code: scraper exit code (0 = ran without fatal error;
                does NOT reflect per-site fetch success — use ok for that)
            results: flat list with one entry per keyword and site pair that
                gave a payload, ordered by keyword then site:
                {keyword, site, payload}. A successful payload is
                {keyword, fields, max_age_hours, filter, count, jobs, source,
                fallback_reason}. A failed pair is listed too: its payload has
                an error key instead of the job fields, and the pair is also in
                errors. Each job holds only the fields named in the payload's
                fields. Canonical fields: site, matched_keyword, title, company,
                company_id, url, location, salary, salary_min, salary_max,
                posted_date, posted_at, work_type, employment_type,
                experience_level, job_id, requirements. A value the site cannot
                extract is null.
            errors: list of {keyword, site, reason, attempts?} for any pair
                that failed. Presence of entries here means ok=false.
                reason values include "fetch failed" (the search page
                download failed; attempts is present) and
                "api failed: <code>" (the request of an API-only site or of
                Indeed failed; no attempts; <code> is for example http_403,
                runtime_error, non_json, graphql_error, not_installed or
                api_disabled).
                `attempts` (when present) lists per-downloader outcomes:
                [{downloader, code, detail}]. Codes:
                  - http_<status>     site rejected request (e.g. http_403)
                  - challenge         anti-bot wall (detail = matched title/marker)
                  - timeout           network or page-load timeout
                  - runtime_error     unexpected exception (detail = class+msg)
                  - not_installed     a dependency is missing: an HTML
                                      downloader's here, a site's own request's
                                      in "api failed: not_installed"
            mongo_id: id of the stored run, or null when the run was not
                stored.
            raw_results: only when include_raw_results is true.
    """
    logger = _get_scraper_logger()
    logger.info(
        "scrape_jobs called sites=%s keywords=%s location=%s max_age_hours=%s",
        sites,
        keywords,
        location,
        max_age_hours,
    )
    target_keywords = strip_and_drop_blank_keywords(keywords)
    if not target_keywords:
        logger.error("scrape_jobs refused: %s", KEYWORDS_REQUIRED)
        return _build_keywords_required_response(sites)
    requested_location = _find_requested_location_option(location)
    if location is not None and requested_location is None:
        unknown_location_message = build_unknown_location_message(location)
        logger.error("scrape_jobs refused: %s", unknown_location_message)
        return _build_refused_scrape_response(sites, unknown_location_message)
    unknown_max_age_message = _find_unknown_max_age_message(max_age_hours)
    if unknown_max_age_message is not None:
        logger.error("scrape_jobs refused: %s", unknown_max_age_message)
        return _build_refused_scrape_response(sites, unknown_max_age_message)
    started_at = time.monotonic()

    try:
        config = _load_app_config()
    except ConfigError as exc:
        logger.error("scrape_jobs config error: %s", exc)
        return {"ok": False, "error": str(exc)}

    target_sites = _choose_passed_or_enabled_sites(sites, config)
    scrape_output = scrape_all_sites(
        config,
        requested_sites=target_sites,
        keywords=target_keywords,
        requested_location=requested_location,
        requested_max_age_hours=max_age_hours,
    )
    response_parts = _build_scrape_response_parts(scrape_output, target_keywords, target_sites)
    scrape_response = _build_scrape_response(
        scrape_output.exit_code, target_keywords, target_sites, response_parts
    )

    duration_seconds = time.monotonic() - started_at
    _log_run_done(scrape_response, duration_seconds)
    _write_scrape_status_file(scrape_response, duration_seconds)

    optional_raw_results = _build_optional_raw_results(
        include_raw_results, response_parts.raw_results
    )
    mongo_id: str | None = None
    if save_run:
        mongo_id = _save_scrape_run(scrape_response)
    else:
        logger.info("scrape_jobs: save_run is off, skipping mongo insert")
    return {**scrape_response, "mongo_id": mongo_id, **optional_raw_results}


def main() -> None:
    mcp.run(transport="streamable-http")


def list_successful_result_entries(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    successful_result_entries: list[dict[str, Any]] = []
    for result_entry in results:
        if _payload_has_error(result_entry["payload"]):
            continue
        successful_result_entries.append(result_entry)
    return successful_result_entries


class _ProxyTestError(Exception):
    pass


@dataclass(frozen=True)
class _ScrapeResponseParts:
    results: list[dict[str, Any]]
    errors: list[dict[str, Any]]
    raw_results: list[dict[str, Any]]


def _load_app_config() -> AppConfig:
    return load_app_config(_build_job_settings_store())


def _build_job_settings_store() -> JobSettingsStore:
    return JobSettingsStore(mongo.read_database())


def _build_site_listing_entry(site: Any) -> dict[str, Any]:
    return {
        "name": site.name,
        "enabled": site.enabled,
        "url_template": site.url_template,
        "sample_url": site.build_search_url_for_keyword(SAMPLE_KEYWORD),
    }


def _convert_stored_settings_to_dict(stored_settings: StoredSettings) -> dict[str, Any]:
    return {
        "version": stored_settings.version,
        "updated_at": stored_settings.updated_at,
        "updated_by": stored_settings.updated_by,
        "settings": stored_settings.settings,
    }


def _list_mandatory_fields() -> list[str]:
    mandatory_fields: list[str] = []
    for field in JOB_FIELD_ORDER:
        if field in MANDATORY_FIELDS:
            mandatory_fields.append(field)
    return mandatory_fields


def _build_sample_response() -> dict[str, Any]:
    return {
        "ok": True,
        "keywords": ["data analyst"],
        "requested_sites": ["jobstreet"],
        "exit_code": 0,
        "results": [_build_sample_result_entry()],
        "errors": [],
        "mongo_id": SAMPLE_MONGO_ID,
    }


def _build_sample_result_entry() -> dict[str, Any]:
    return {
        "keyword": "data analyst",
        "site": "jobstreet",
        "payload": _build_sample_site_payload(),
    }


def _build_sample_site_payload() -> dict[str, Any]:
    return {
        "keyword": "data analyst",
        "fields": list(JOB_FIELD_ORDER),
        "max_age_hours": 24,
        "filter": {"location": ["jakarta"]},
        "count": 1,
        "jobs": [_build_sample_job()],
        "source": "api",
        "fallback_reason": None,
    }


def _build_sample_job() -> dict[str, Any]:
    empty_job: dict[str, Any] = dict.fromkeys(JOB_FIELD_ORDER)
    return {
        **empty_job,
        "site": "jobstreet",
        "matched_keyword": "data analyst",
        "title": "Data Analyst",
        "company": "ACME",
        "url": "https://id.jobstreet.com/job/123",
    }


def _save_settings_and_build_response(
    save_settings: Callable[[], StoredSettings],
) -> dict[str, Any]:
    try:
        stored_settings = save_settings()
    except SettingsConflictError as exc:
        return {"ok": False, "reason": "conflict", "message": str(exc)}
    except (SettingsMissingError, SettingsUnavailableError) as exc:
        return {"ok": False, "reason": "unavailable", "message": str(exc)}
    except ConfigError as exc:
        return {"ok": False, "reason": "invalid", "message": str(exc)}
    return {"ok": True, **_convert_stored_settings_to_dict(stored_settings)}


def _choose_passed_or_default_test_url(passed_url: str | None) -> str:
    test_url = DEFAULT_PROXY_TEST_URL
    if passed_url and passed_url.strip():
        test_url = passed_url.strip()
    scheme = urlparse(test_url).scheme
    if scheme not in ALLOWED_TEST_URL_SCHEMES:
        raise _ProxyTestError(f"url must be http(s), got scheme={scheme!r}")
    return test_url


def _choose_passed_or_config_proxy_url(passed_proxy_url: str | None) -> tuple[str, bool]:
    stripped_proxy_url = (passed_proxy_url or "").strip()
    if stripped_proxy_url:
        return stripped_proxy_url, False

    try:
        config = _load_app_config()
    except ConfigError as exc:
        _get_scraper_logger().warning("test_proxy_connection config error: %s", exc)
        raise _ProxyTestError(str(exc)) from exc
    if not config.proxy:
        raise _ProxyTestError(NO_PROXY_MESSAGE)
    return config.proxy.url, True


def _probe_proxy_http(proxy_url: str, test_url: str) -> dict[str, Any]:
    try:
        from curl_cffi import requests as cffi_requests  # type: ignore[attr-defined]
    except Exception as exc:
        return {
            "ok": False,
            "error": f"curl_cffi not available: {_format_exception_with_type(exc)}",
        }

    try:
        http_response = cffi_requests.get(
            test_url,
            impersonate=CHROME_IMPERSONATE,
            headers={"User-Agent": USER_AGENT, "Accept-Language": ACCEPT_LANGUAGE},
            timeout=PROXY_TEST_TIMEOUT_SEC,
            proxies={"http": proxy_url, "https": proxy_url},
        )
    except Exception as exc:
        return {"ok": False, "error": _format_exception_with_type(exc)}

    return _build_probe_result(http_response, test_url)


def _format_exception_with_type(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


def _build_probe_result(http_response: Any, test_url: str) -> dict[str, Any]:
    http_status = http_response.status_code
    response_excerpt = (http_response.text or "")[:PROBE_EXCERPT_CHARS]
    probe_result: dict[str, Any] = {
        "ok": http_status == HTTP_OK,
        "http_status": http_status,
        "test_url": test_url,
        "response_excerpt": response_excerpt,
    }
    if http_status != HTTP_OK:
        return {**probe_result, "error": f"HTTP {http_status}"}

    egress_ip = _read_egress_ip(http_response, response_excerpt)
    if not egress_ip:
        return probe_result
    return {**probe_result, "egress_ip": egress_ip}


def _read_egress_ip(http_response: Any, response_excerpt: str) -> str | None:
    json_egress_ip = _read_json_egress_ip(http_response, response_excerpt)
    if json_egress_ip is not None:
        return json_egress_ip
    if response_excerpt and len(response_excerpt) < PLAIN_IP_MAX_CHARS:
        return response_excerpt.strip()
    return None


def _read_json_egress_ip(http_response: Any, response_excerpt: str) -> str | None:
    if not _looks_like_json(http_response, response_excerpt):
        return None
    try:
        response_body = json.loads(http_response.text or "")
    except json.JSONDecodeError:
        return None
    if not isinstance(response_body, dict):
        return None

    ip_address = response_body.get("ip")
    if isinstance(ip_address, str):
        return ip_address
    origin_addresses = response_body.get("origin")
    if isinstance(origin_addresses, str):
        return origin_addresses.split(",")[0].strip()
    return None


def _looks_like_json(http_response: Any, response_excerpt: str) -> bool:
    content_type = (http_response.headers.get("content-type") or "").lower()
    if "json" in content_type:
        return True
    return response_excerpt.strip().startswith("{")


def _log_proxy_test_result(proxy_test_result: dict[str, Any]) -> None:
    logger = _get_scraper_logger()
    if not proxy_test_result.get("ok"):
        logger.warning("test_proxy_connection failed: %s", proxy_test_result.get("error"))
        return
    logger.info(
        "test_proxy_connection ok duration_ms=%s egress_ip=%s",
        proxy_test_result["duration_ms"],
        proxy_test_result.get("egress_ip"),
    )


def _build_keywords_required_response(passed_sites: list[str] | None) -> dict[str, Any]:
    return _build_refused_scrape_response(passed_sites, KEYWORDS_REQUIRED)


def _find_requested_location_option(location: str | None) -> str | None:
    if location is None:
        return None
    return find_filter_location_option(location)


def _find_unknown_max_age_message(max_age_hours: int | None) -> str | None:
    if max_age_hours is None:
        return None
    if is_max_age_option(max_age_hours):
        return None
    return build_unknown_max_age_message(max_age_hours)


def _build_refused_scrape_response(passed_sites: list[str] | None, reason: str) -> dict[str, Any]:
    requested_sites: list[str] = []
    if passed_sites:
        requested_sites = list(passed_sites)
    return {
        "ok": False,
        "keywords": [],
        "requested_sites": requested_sites,
        "exit_code": 1,
        "results": [],
        "errors": [{"keyword": None, "site": None, "reason": reason}],
        "mongo_id": None,
    }


def _choose_passed_or_enabled_sites(passed_sites: list[str] | None, config: AppConfig) -> list[str]:
    if passed_sites:
        return list(passed_sites)
    return list(config.list_enabled_site_names())


def _build_scrape_response_parts(
    scrape_output: RunResult, keywords: list[str], sites: list[str]
) -> _ScrapeResponseParts:
    keyword_site_pairs = list(product(keywords, sites))
    results, raw_results = _build_results_and_raw_results(scrape_output, keyword_site_pairs)
    return _ScrapeResponseParts(
        results=results,
        errors=_build_keyword_site_errors(scrape_output, keyword_site_pairs),
        raw_results=raw_results,
    )


def _build_results_and_raw_results(
    scrape_output: RunResult, keyword_site_pairs: list[tuple[str, str]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    results: list[dict[str, Any]] = []
    raw_results: list[dict[str, Any]] = []
    for keyword, site in keyword_site_pairs:
        filtered_and_raw_payloads = scrape_output.get_payloads_for_keyword_and_site(keyword, site)
        if filtered_and_raw_payloads is None:
            continue
        results.append(_build_payload_entry(keyword, site, filtered_and_raw_payloads.filtered))
        raw_results.append(_build_payload_entry(keyword, site, filtered_and_raw_payloads.raw))
    return results, raw_results


def _build_payload_entry(keyword: str, site: str, site_payload: dict[str, Any]) -> dict[str, Any]:
    return {"keyword": keyword, "site": site, "payload": site_payload}


def _build_keyword_site_errors(
    scrape_output: RunResult, keyword_site_pairs: list[tuple[str, str]]
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for keyword, site in keyword_site_pairs:
        filtered_and_raw_payloads = scrape_output.get_payloads_for_keyword_and_site(keyword, site)
        if filtered_and_raw_payloads is None:
            errors.append(_build_missing_result_error(keyword, site, scrape_output))
            continue
        if _payload_has_error(filtered_and_raw_payloads.filtered):
            errors.append(
                _build_site_payload_error(keyword, site, filtered_and_raw_payloads.filtered)
            )
    return errors


def _build_missing_result_error(
    keyword: str, site: str, scrape_output: RunResult
) -> dict[str, Any]:
    no_result_reason = (
        f"scraper returned no result for this pair (exit code {scrape_output.exit_code})"
    )
    return {"keyword": keyword, "site": site, "reason": scrape_output.error or no_result_reason}


def _payload_has_error(site_payload: dict[str, Any]) -> bool:
    return "error" in site_payload


def _build_site_payload_error(
    keyword: str, site: str, site_payload: dict[str, Any]
) -> dict[str, Any]:
    payload_error: dict[str, Any] = {
        "keyword": keyword,
        "site": site,
        "reason": str(site_payload.get("error")),
    }
    attempts = site_payload.get("attempts")
    if not isinstance(attempts, list):
        return payload_error
    return {**payload_error, "attempts": attempts}


def _build_scrape_response(
    exit_code: int, keywords: list[str], sites: list[str], response_parts: _ScrapeResponseParts
) -> dict[str, Any]:
    return {
        "ok": len(response_parts.errors) == 0,
        "keywords": keywords,
        "requested_sites": sites,
        "exit_code": exit_code,
        "results": response_parts.results,
        "errors": response_parts.errors,
    }


def _log_run_done(scrape_response: dict[str, Any], duration_seconds: float) -> None:
    _get_scraper_logger().info(
        "scrape_jobs done ok=%s errors=%d jobs=%d duration=%.1fs",
        scrape_response["ok"],
        len(scrape_response["errors"]),
        _count_jobs(scrape_response["results"]),
        duration_seconds,
    )


def _write_scrape_status_file(scrape_response: dict[str, Any], duration_seconds: float) -> None:
    now = datetime.now(UTC).isoformat()
    errors: list[dict[str, Any]] = scrape_response.get("errors", [])
    results: list[dict[str, Any]] = scrape_response.get("results", [])
    site_statuses = {
        **_read_saved_site_statuses(),
        **_build_ok_site_statuses(results, now),
        **_build_failed_site_statuses(errors, now),
    }
    scrape_status = {
        "last_run": _build_last_run(scrape_response, errors, duration_seconds, now),
        "last_error": _build_last_error(errors, now),
        "per_site": site_statuses,
    }
    _write_json_atomically(_STATUS_PATH, scrape_status)


def _read_saved_site_statuses() -> dict[str, Any]:
    if not _STATUS_PATH.exists():
        return {}
    try:
        saved_scrape_status = json.loads(_STATUS_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    return saved_scrape_status.get("per_site", {})


def _build_ok_site_statuses(results: list[dict[str, Any]], now: str) -> dict[str, Any]:
    site_statuses: dict[str, Any] = {}
    for result_entry in list_successful_result_entries(results):
        site_name = result_entry.get("site")
        if not site_name:
            continue
        site_statuses[site_name] = _build_site_status(
            now=now,
            last_status="ok",
            job_count=_count_payload_jobs(result_entry["payload"]),
            last_error=None,
        )
    return site_statuses


def _count_payload_jobs(site_payload: dict[str, Any]) -> int:
    jobs = site_payload.get("jobs")
    if not isinstance(jobs, list):
        return 0
    return len(jobs)


def _build_failed_site_statuses(errors: list[dict[str, Any]], now: str) -> dict[str, Any]:
    site_statuses: dict[str, Any] = {}
    for error in errors:
        site_name = error.get("site")
        if not site_name:
            continue
        site_statuses[site_name] = _build_site_status(
            now=now, last_status="error", job_count=0, last_error=error.get("reason")
        )
    return site_statuses


def _build_site_status(
    *, now: str, last_status: str, job_count: int, last_error: str | None
) -> dict[str, Any]:
    return {
        "last_run_at": now,
        "last_status": last_status,
        "last_job_count": job_count,
        "last_error": last_error,
    }


def _build_last_run(
    scrape_response: dict[str, Any],
    errors: list[dict[str, Any]],
    duration_seconds: float,
    now: str,
) -> dict[str, Any]:
    return {
        "timestamp": now,
        "ok": scrape_response.get("ok", False),
        "duration_seconds": round(duration_seconds, 2),
        "keywords": scrape_response.get("keywords", []),
        "sites": scrape_response.get("requested_sites", []),
        "total_jobs": _count_jobs(scrape_response.get("results", [])),
        "error_count": len(errors),
        "errors": errors,
    }


def _count_jobs(results: list[dict[str, Any]]) -> int:
    total_jobs = 0
    for result_entry in list_successful_result_entries(results):
        total_jobs += _count_payload_jobs(result_entry["payload"])
    return total_jobs


def _build_last_error(errors: list[dict[str, Any]], now: str) -> dict[str, Any] | None:
    if not errors:
        return None
    return {**errors[-1], "timestamp": now}


def _write_json_atomically(target_path: Path, json_content: dict[str, Any]) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = target_path.with_name(f"{target_path.name}.{os.getpid()}.tmp")
    temporary_path.write_text(json.dumps(json_content, indent=2))
    os.replace(temporary_path, target_path)


def _build_optional_raw_results(
    include_raw_results: bool, raw_results: list[dict[str, Any]]
) -> dict[str, Any]:
    if not include_raw_results:
        return {}
    return {"raw_results": raw_results}


def _save_scrape_run(scrape_response: dict[str, Any]) -> str | None:
    logger = _get_scraper_logger()
    try:
        mongo_id = mongo.insert_run(_build_run_document(scrape_response))
    except Exception as exc:
        logger.error("scrape_jobs: mongo insert failed: %s", exc)
        return None
    logger.info("scrape_jobs: mongo insert ok id=%s", mongo_id)
    return mongo_id


def _build_run_document(scrape_response: dict[str, Any]) -> dict[str, Any]:
    results: list[dict[str, Any]] = scrape_response["results"]
    return {
        "run_metadata": {
            "ok": scrape_response["ok"],
            "exit_code": scrape_response["exit_code"],
            "keywords": scrape_response["keywords"],
            "requested_sites": scrape_response["requested_sites"],
            "errors": scrape_response["errors"],
            "per_site_counts": _build_per_site_counts(results),
            "per_site_sources": _build_per_site_sources(results),
        },
        "results": results,
        "note": _build_failure_note(scrape_response["errors"]),
    }


def _build_per_site_counts(results: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    per_site_counts: dict[str, dict[str, int]] = {}
    for result_entry in list_successful_result_entries(results):
        site_counts = per_site_counts.setdefault(result_entry["site"], {})
        site_counts[result_entry["keyword"]] = _count_payload_jobs(result_entry["payload"])
    return per_site_counts


def _build_per_site_sources(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    per_site_sources: list[dict[str, Any]] = []
    for result_entry in results:
        site_payload = result_entry.get("payload")
        if not isinstance(site_payload, dict):
            continue
        per_site_sources.append(_build_site_source(result_entry, site_payload))
    return per_site_sources


def _build_site_source(
    result_entry: dict[str, Any], site_payload: dict[str, Any]
) -> dict[str, Any]:
    return {
        "site": result_entry.get("site"),
        "keyword": result_entry.get("keyword"),
        "source": site_payload.get("source", "html"),
        "fallback_reason": site_payload.get("fallback_reason"),
    }


def _build_failure_note(errors: list[dict[str, Any]]) -> str | None:
    if not errors:
        return None
    reasons = [_format_error_reason(error) for error in errors]
    return f"scrape failed — {'; '.join(reasons)}"


def _format_error_reason(error: dict[str, Any]) -> str:
    site = error.get("site", "?")
    reason = error.get("reason", "unknown")
    return f"{site}: {reason}"


if __name__ == "__main__":
    main()
