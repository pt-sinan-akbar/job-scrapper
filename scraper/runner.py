from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import Any
from urllib.parse import urlparse

from .api.client import DETAIL_DELAY_SECONDS, ApiClient, ApiError
from .api.registry import API_SOURCES
from .api.source import ApiSource, search_all
from .config_loader import (
    ALLOWED_URL_HOSTS,
    ApiConfig,
    AppConfig,
    SiteConfig,
    build_keyword_slug,
    read_concurrency_from_env,
)
from .html_downloaders import (
    CloudscraperHtmlDownloader,
    CurlCffiHtmlDownloader,
    FallbackHtmlDownloader,
    PlaywrightHtmlDownloader,
)
from .log import get_scraper_logger, hide_proxy_password
from .sites import SCRAPERS, Scraper
from .sites._dates import parse_to_iso
from .sites._filter import filter_reason, project_jobs
from .types import CANONICAL_FIELDS, Job

_LOG = get_scraper_logger()

KEYWORDS_REQUIRED = "keywords are required"

_MAX_REQUIREMENT_WORKERS = 4
_SOURCE_API = "api"
_SOURCE_HTML = "html"
_API_DISABLED = "api_disabled"

Payload = dict[str, Any]
KeywordSitePair = tuple[str, str]

_SearchJobsViaApi = Callable[[], list[Job]]
_ReadRequirementsViaApi = Callable[[Job], str | None]


@dataclass(frozen=True)
class FilteredAndRawPayloads:
    filtered: Payload
    raw: Payload


@dataclass(frozen=True)
class RunResult:
    exit_code: int
    results: Mapping[KeywordSitePair, FilteredAndRawPayloads] = field(
        default_factory=lambda: MappingProxyType({})
    )
    error: str | None = None

    def get_payloads_for_keyword_and_site(
        self, keyword: str, site: str
    ) -> FilteredAndRawPayloads | None:
        return self.results.get((keyword, site))


@dataclass(frozen=True)
class _ApiOutcome:
    jobs: list[Job] | None = None
    fallback_reason: str | None = None


@dataclass(frozen=True)
class _UnfilteredJobsFromApiOrHtml:
    jobs: list[Job]
    source: str
    fallback_reason: str | None


def scrape_all_sites(
    config: AppConfig,
    requested_sites: Iterable[str] = (),
    keywords: Iterable[str] | None = None,
) -> RunResult:
    sites_to_scrape = _choose_requested_or_enabled_sites(config, requested_sites)
    cleaned_keywords = strip_and_drop_blank_keywords(keywords)
    input_error = _find_input_error(sites_to_scrape, cleaned_keywords)
    if input_error is not None:
        _LOG.error("[runner] %s", input_error)
        return RunResult(exit_code=1, error=input_error)

    # Example: [("python", "jobstreet"), ("python", "glints"), ("devops", "jobstreet"), ("devops", "glints")]
    keyword_site_pairs = _build_keyword_site_pairs(sites_to_scrape, cleaned_keywords)
    proxy_url = _read_proxy_url_from_config(config)
    html_downloader = FallbackHtmlDownloader(
        [
            CurlCffiHtmlDownloader(proxy=proxy_url),
            CloudscraperHtmlDownloader(proxy=proxy_url),
            PlaywrightHtmlDownloader(proxy=proxy_url),
        ]
    )

    payloads_by_keyword_site_pair = _scrape_keyword_site_pairs_concurrently(
        config, keyword_site_pairs, html_downloader, proxy_url
    )
    return RunResult(exit_code=0, results=MappingProxyType(payloads_by_keyword_site_pair))


def strip_and_drop_blank_keywords(keywords: Iterable[str] | None) -> list[str]:
    cleaned_keywords: list[str] = []
    if not keywords:
        return cleaned_keywords
    for keyword in keywords:
        stripped_keyword = keyword.strip()
        if stripped_keyword:
            cleaned_keywords.append(stripped_keyword)
    return cleaned_keywords


def scrape_site_for_keyword(
    scraper: Scraper,
    html_downloader: FallbackHtmlDownloader,
    keyword: str,
    fields: frozenset[str],
    max_age_hours: int | None,
    content_filter: dict[str, list[str]],
    *,
    search_jobs_via_api: _SearchJobsViaApi | None = None,
    read_requirements_via_api: _ReadRequirementsViaApi | None = None,
) -> FilteredAndRawPayloads:
    # Example: "jobstreet:software-engineer"
    label = f"{scraper.name}:{build_keyword_slug(keyword)}"

    jobs_or_error_payloads = _search_jobs_via_api_or_html(
        scraper, html_downloader, keyword, label, search_jobs_via_api
    )
    # A FilteredAndRawPayloads here is an error result: no jobs could be fetched, so return it as is
    if isinstance(jobs_or_error_payloads, FilteredAndRawPayloads):
        return jobs_or_error_payloads
    unfiltered_jobs = jobs_or_error_payloads

    _LOG.info(
        "[%s] parsed %d job(s) via %s", label, len(unfiltered_jobs.jobs), unfiltered_jobs.source
    )

    _fill_missing_matched_keyword_and_posted_at(unfiltered_jobs.jobs, keyword)
    raw_payload = _build_raw_payload(unfiltered_jobs, keyword, label)

    jobs = _drop_stale_jobs(unfiltered_jobs.jobs, max_age_hours, label)
    jobs = _drop_jobs_failing_content_filter(jobs, content_filter, label)
    jobs = _cap_jobs_to_limit(jobs, scraper.limit, label)
    requirements_reader = _pick_requirements_reader_for_source(
        unfiltered_jobs.source, read_requirements_via_api
    )
    _fill_requirements_for_jobs(
        jobs, fields, html_downloader, scraper, read_requirements_via_api=requirements_reader
    )

    filtered_payload = _build_filtered_payload(
        jobs, unfiltered_jobs, keyword, fields, max_age_hours, content_filter
    )
    _LOG.info("[%s] done with %d job(s)", label, filtered_payload["count"])
    return FilteredAndRawPayloads(filtered=filtered_payload, raw=raw_payload)


def build_api_search_and_requirements_functions(
    build_api_source: Callable[[Any], ApiSource],
    api_config: ApiConfig,
    keyword: str,
    *,
    proxy_url: str | None,
    max_age_hours: int | None,
    limit: int,
    build_api_client: Callable[..., Any] = ApiClient,
) -> tuple[_SearchJobsViaApi, _ReadRequirementsViaApi]:
    api_source_for_search = build_api_source(
        _build_api_client_for_search(build_api_client, api_config, proxy_url)
    )
    api_client_for_requirements = build_api_client(proxy=proxy_url, delay=DETAIL_DELAY_SECONDS)
    api_source_for_requirements = build_api_source(api_client_for_requirements)
    locations = api_config.locations
    country_wide = api_config.country_wide

    def search_jobs_via_api() -> list[Job]:
        return search_all(
            api_source_for_search, keyword, locations, country_wide, max_age_hours, limit
        )

    return search_jobs_via_api, api_source_for_requirements.detail


def build_keyword_site_pair_error_payloads(keyword: str, reason: str) -> FilteredAndRawPayloads:
    return FilteredAndRawPayloads(
        filtered={"error": reason, "keyword": keyword, "source": None, "fallback_reason": None},
        raw=_build_empty_raw_payload(keyword, reason),
    )


def _choose_requested_or_enabled_sites(
    config: AppConfig, requested_sites: Iterable[str]
) -> list[str]:
    requested_list = list(requested_sites)
    if requested_list:
        return requested_list
    return list(config.list_enabled_site_names())


def _find_input_error(sites_to_scrape: list[str], keywords: list[str]) -> str | None:
    if not keywords:
        return KEYWORDS_REQUIRED
    if not sites_to_scrape:
        return "no sites selected (none enabled in config and none requested)"
    unknown_site_names = _find_unknown_sites(sites_to_scrape)
    if unknown_site_names:
        return f"unknown sites: {', '.join(unknown_site_names)}. available: {', '.join(SCRAPERS)}"
    return None


def _find_unknown_sites(site_names: list[str]) -> list[str]:
    unknown_site_names: list[str] = []
    for site_name in site_names:
        if site_name not in SCRAPERS:
            unknown_site_names.append(site_name)
    return unknown_site_names


def _build_keyword_site_pairs(sites: list[str], keywords: list[str]) -> list[KeywordSitePair]:
    keyword_site_pairs: list[KeywordSitePair] = []
    for keyword in keywords:
        for site in sites:
            keyword_site_pairs.append((keyword, site))
    return keyword_site_pairs


def _read_proxy_url_from_config(config: AppConfig) -> str | None:
    if not config.proxy:
        return None
    proxy_url = config.proxy.url
    if proxy_url:
        _LOG.info("[runner] using proxy: %s", hide_proxy_password(proxy_url))
    return proxy_url


def _scrape_keyword_site_pairs_concurrently(
    config: AppConfig,
    keyword_site_pairs: list[KeywordSitePair],
    html_downloader: FallbackHtmlDownloader,
    proxy_url: str | None,
) -> dict[KeywordSitePair, FilteredAndRawPayloads]:
    payloads_by_keyword_site_pair: dict[KeywordSitePair, FilteredAndRawPayloads] = {}
    worker_count = max(1, min(read_concurrency_from_env(), len(keyword_site_pairs)))
    if worker_count == 1:
        for keyword_site_pair in keyword_site_pairs:
            payloads_by_keyword_site_pair[keyword_site_pair] = _scrape_keyword_site_pair(
                config, keyword_site_pair, html_downloader, proxy_url
            )
        return payloads_by_keyword_site_pair

    _LOG.info(
        "[runner] running %d (keyword,site) pair(s) with concurrency=%d",
        len(keyword_site_pairs),
        worker_count,
    )
    with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="scraper") as thread_pool:
        background_scrape_tasks: dict[KeywordSitePair, Future[FilteredAndRawPayloads]] = {}
        for keyword_site_pair in keyword_site_pairs:
            background_scrape_task = thread_pool.submit(
                _scrape_keyword_site_pair, config, keyword_site_pair, html_downloader, proxy_url
            )
            background_scrape_tasks[keyword_site_pair] = background_scrape_task

        for keyword_site_pair, background_scrape_task in background_scrape_tasks.items():
            payloads_by_keyword_site_pair[keyword_site_pair] = background_scrape_task.result()
    return payloads_by_keyword_site_pair


def _scrape_keyword_site_pair(
    config: AppConfig,
    keyword_site_pair: KeywordSitePair,
    html_downloader: FallbackHtmlDownloader,
    proxy_url: str | None,
) -> FilteredAndRawPayloads:
    keyword, site_name = keyword_site_pair
    try:
        site_config = config.find_site_config(site_name)
        if site_config is None:
            _LOG.warning("[runner] '%s' has no entry in the job settings; skipping", site_name)
            return build_keyword_site_pair_error_payloads(
                keyword, "skipped: site has no entry in the job settings"
            )

        scraper = SCRAPERS[site_name](
            url=site_config.build_search_url_for_keyword(keyword), limit=site_config.limit
        )
        search_jobs_via_api, read_requirements_via_api = _build_api_functions_for_site(
            scraper, site_config, site_name, keyword, proxy_url
        )
        return scrape_site_for_keyword(
            scraper,
            html_downloader,
            keyword,
            config.list_saved_fields(),
            site_config.max_age_hours,
            site_config.filter,
            search_jobs_via_api=search_jobs_via_api,
            read_requirements_via_api=read_requirements_via_api,
        )
    except Exception as exc:
        _LOG.exception("[%s:%s] pair crashed", site_name, build_keyword_slug(keyword))
        return build_keyword_site_pair_error_payloads(keyword, f"crashed: {type(exc).__name__}")


def _build_api_functions_for_site(
    scraper: Scraper,
    site_config: SiteConfig,
    site_name: str,
    keyword: str,
    proxy_url: str | None,
) -> tuple[_SearchJobsViaApi | None, _ReadRequirementsViaApi | None]:
    api_config = site_config.api
    if api_config is None:
        return None, None
    if not _is_api_usable_for_site(scraper, api_config, site_name):
        return None, None
    return build_api_search_and_requirements_functions(
        API_SOURCES[site_name],
        api_config,
        keyword,
        proxy_url=proxy_url,
        max_age_hours=site_config.max_age_hours,
        limit=site_config.limit,
    )


def _is_api_usable_for_site(scraper: Scraper, api_config: ApiConfig, site_name: str) -> bool:
    if not api_config.enabled:
        return False
    if site_name not in API_SOURCES:
        return False
    if not scraper.api_only:
        return True
    if api_config.locations:
        return True
    return api_config.country_wide


def _search_jobs_via_api_or_html(
    scraper: Scraper,
    html_downloader: FallbackHtmlDownloader,
    keyword: str,
    label: str,
    search_jobs_via_api: _SearchJobsViaApi | None,
) -> _UnfilteredJobsFromApiOrHtml | FilteredAndRawPayloads:
    api_outcome = _search_jobs_via_api_and_catch_errors(search_jobs_via_api, label)
    # jobs is None only when the API was not used or it failed
    # An empty list means the API worked and found no jobs, so it is still returned here
    if api_outcome.jobs is not None:
        return _UnfilteredJobsFromApiOrHtml(api_outcome.jobs, _SOURCE_API, None)

    fallback_reason = api_outcome.fallback_reason
    if scraper.api_only:
        return _build_api_only_failure_payloads(keyword, fallback_reason)

    if fallback_reason is not None:
        _LOG.warning("[%s] falling back to html (%s)", label, fallback_reason)
    html_jobs_or_error_payloads = _scrape_jobs_from_html(
        scraper, html_downloader, keyword, label, fallback_reason
    )
    if isinstance(html_jobs_or_error_payloads, FilteredAndRawPayloads):
        return html_jobs_or_error_payloads
    return _UnfilteredJobsFromApiOrHtml(html_jobs_or_error_payloads, _SOURCE_HTML, fallback_reason)


def _search_jobs_via_api_and_catch_errors(
    search_jobs_via_api: _SearchJobsViaApi | None, label: str
) -> _ApiOutcome:
    if search_jobs_via_api is None:
        return _ApiOutcome()
    try:
        jobs = search_jobs_via_api()
        _LOG.info("[%s] api returned %d job(s)", label, len(jobs))
    except ApiError as exc:
        _LOG.warning("[%s] api failed (%s)", label, exc.code)
        _LOG.debug("[%s] api failure detail: %s", label, exc.detail)
        return _ApiOutcome(fallback_reason=exc.code)
    except Exception as exc:
        _LOG.exception("[%s] api crashed", label)
        return _ApiOutcome(fallback_reason=f"unexpected_error:{type(exc).__name__}")
    return _ApiOutcome(jobs=jobs)


def _build_api_only_failure_payloads(
    keyword: str, fallback_reason: str | None
) -> FilteredAndRawPayloads:
    if not fallback_reason:
        return _build_api_failure_payloads(keyword, _API_DISABLED)
    return _build_api_failure_payloads(keyword, fallback_reason)


def _build_api_failure_payloads(keyword: str, reason: str) -> FilteredAndRawPayloads:
    error = f"api failed: {reason}"
    return FilteredAndRawPayloads(
        filtered={
            "error": error,
            "keyword": keyword,
            "source": _SOURCE_API,
            "fallback_reason": None,
        },
        raw=_build_empty_raw_payload(keyword, error),
    )


def _scrape_jobs_from_html(
    scraper: Scraper,
    html_downloader: FallbackHtmlDownloader,
    keyword: str,
    label: str,
    fallback_reason: str | None,
) -> list[Job] | FilteredAndRawPayloads:
    if not scraper.requires_search_html:
        _LOG.info("[%s] site makes its own request, search page not downloaded", label)
        return _parse_jobs_from_site_own_request(scraper, keyword, label)

    _LOG.info("[%s] fetching %s", label, scraper.url)
    search_html_download = html_downloader.download_html(scraper.url)
    search_html = search_html_download.html
    if not search_html:
        _LOG.error("[%s] FAILED: no html", label)
        attempts = [attempt.to_dict() for attempt in search_html_download.attempts]
        return _build_html_download_failure_payloads(scraper, keyword, attempts, fallback_reason)

    _LOG.info("[%s] fetched search html (%d bytes)", label, len(search_html))
    jobs_from_search_page = scraper.parse(search_html)
    if not jobs_from_search_page:
        _LOG.warning("[%s] html source returned 0 jobs; the page layout may have changed", label)
    return jobs_from_search_page


def _parse_jobs_from_site_own_request(
    scraper: Scraper, keyword: str, label: str
) -> list[Job] | FilteredAndRawPayloads:
    try:
        return scraper.parse("")
    except ApiError as exc:
        _LOG.warning("[%s] site request failed (%s)", label, exc.code)
        _LOG.debug("[%s] site request failure detail: %s", label, exc.detail)
        return _build_api_failure_payloads(keyword, exc.code)


def _build_html_download_failure_payloads(
    scraper: Scraper, keyword: str, attempts: list[Payload], fallback_reason: str | None
) -> FilteredAndRawPayloads:
    return FilteredAndRawPayloads(
        filtered={
            "error": "fetch failed",
            "url": scraper.url,
            "keyword": keyword,
            "attempts": attempts,
            "source": _SOURCE_HTML,
            "fallback_reason": fallback_reason,
        },
        raw=_build_empty_raw_payload(keyword, "fetch failed"),
    )


def _fill_missing_matched_keyword_and_posted_at(jobs: list[Job], keyword: str) -> None:
    for job in jobs:
        if job.get("matched_keyword") is None:
            job["matched_keyword"] = keyword
        if job.get("posted_at") is None:
            job["posted_at"] = parse_to_iso(job.get("posted_date"))


def _build_raw_payload(
    unfiltered_jobs: _UnfilteredJobsFromApiOrHtml, keyword: str, label: str
) -> Payload:
    raw_jobs = project_jobs(unfiltered_jobs.jobs, CANONICAL_FIELDS)
    _LOG.info("[%s] kept %d raw job(s)", label, len(raw_jobs))
    return {
        "keyword": keyword,
        "fields": sorted(CANONICAL_FIELDS),
        "count": len(raw_jobs),
        "jobs": raw_jobs,
        "source": unfiltered_jobs.source,
        "fallback_reason": unfiltered_jobs.fallback_reason,
    }


def _drop_stale_jobs(jobs: list[Job], max_age_hours: int | None, label: str) -> list[Job]:
    if max_age_hours is None:
        return jobs

    cutoff = datetime.now(UTC) - timedelta(hours=max_age_hours)
    recent_jobs: list[Job] = []
    for job in jobs:
        if _is_within_max_age(job, cutoff):
            recent_jobs.append(job)
            continue
        _LOG.debug(
            "[%s] drop stale: %r posted_at=%s < cutoff=%s",
            label,
            job.get("title"),
            job.get("posted_at"),
            cutoff.isoformat(),
        )
    _LOG.info(
        "[%s] max_age=%dh cutoff=%s kept %d/%d (dropped %d stale)",
        label,
        max_age_hours,
        cutoff.isoformat(),
        len(recent_jobs),
        len(jobs),
        len(jobs) - len(recent_jobs),
    )
    return recent_jobs


def _is_within_max_age(job: Job, cutoff: datetime) -> bool:
    posted_at_text = job.get("posted_at")
    if not isinstance(posted_at_text, str):
        return True
    try:
        posted_at = datetime.fromisoformat(posted_at_text)
    except ValueError:
        return True
    if posted_at.tzinfo is None:
        posted_at = posted_at.replace(tzinfo=UTC)
    return posted_at >= cutoff


def _drop_jobs_failing_content_filter(
    jobs: list[Job], content_filter: dict[str, list[str]], label: str
) -> list[Job]:
    if not content_filter:
        return jobs

    jobs_passing_filter: list[Job] = []
    for job in jobs:
        reason = filter_reason(job, content_filter)
        if reason is None:
            jobs_passing_filter.append(job)
            continue
        _LOG.debug("[%s] drop filter: %r %s", label, job.get("title"), reason)
    _LOG.info(
        "[%s] filter=%s kept %d/%d (dropped %d)",
        label,
        content_filter,
        len(jobs_passing_filter),
        len(jobs),
        len(jobs) - len(jobs_passing_filter),
    )
    return jobs_passing_filter


def _cap_jobs_to_limit(jobs: list[Job], limit: int, label: str) -> list[Job]:
    if len(jobs) <= limit:
        return jobs
    _LOG.info("[%s] capping %d job(s) to limit=%d", label, len(jobs), limit)
    return jobs[:limit]


def _pick_requirements_reader_for_source(
    source: str, read_requirements_via_api: _ReadRequirementsViaApi | None
) -> _ReadRequirementsViaApi | None:
    if source != _SOURCE_API:
        return None
    return read_requirements_via_api


def _fill_requirements_for_jobs(
    jobs: list[Job],
    fields: frozenset[str],
    html_downloader: FallbackHtmlDownloader,
    scraper: Scraper,
    read_requirements_via_api: _ReadRequirementsViaApi | None = None,
) -> None:
    if "requirements" not in fields:
        return
    if not jobs:
        return
    if scraper.api_only:
        return

    _LOG.info("[%s] fetching requirements for %d job(s)", scraper.name, len(jobs))
    worker_count = min(_MAX_REQUIREMENT_WORKERS, len(jobs))
    with ThreadPoolExecutor(max_workers=worker_count) as thread_pool:
        job_index_by_running_requirements_read: dict[Future[str | None], int] = {}
        for job_index, job in enumerate(jobs):
            running_requirements_read = thread_pool.submit(
                _find_requirements_for_job, job, html_downloader, scraper, read_requirements_via_api
            )
            job_index_by_running_requirements_read[running_requirements_read] = job_index

        for finished_requirements_read in as_completed(job_index_by_running_requirements_read):
            finished_job_index = job_index_by_running_requirements_read[finished_requirements_read]
            jobs[finished_job_index]["requirements"] = _read_future_result_or_none(
                finished_requirements_read, scraper.name
            )


def _find_requirements_for_job(
    job: Job,
    html_downloader: FallbackHtmlDownloader,
    scraper: Scraper,
    read_requirements_via_api: _ReadRequirementsViaApi | None,
) -> str | None:
    existing_requirements = job.get("requirements")
    if _has_text(existing_requirements):
        return existing_requirements
    requirements_from_api = _read_requirements_from_api(job, scraper, read_requirements_via_api)
    if requirements_from_api:
        return requirements_from_api
    return _read_requirements_from_job_page(job, html_downloader, scraper)


def _has_text(text_or_other_type: object) -> bool:
    if not isinstance(text_or_other_type, str):
        return False
    return bool(text_or_other_type.strip())


def _read_requirements_from_api(
    job: Job, scraper: Scraper, read_requirements_via_api: _ReadRequirementsViaApi | None
) -> str | None:
    if read_requirements_via_api is None:
        return None
    try:
        return read_requirements_via_api(job)
    except Exception as exc:
        _LOG.warning(
            "[%s] requirements api failed for %s (%s)",
            scraper.name,
            job.get("url"),
            _read_short_failure_reason(exc),
        )
        _LOG.debug(
            "[%s] requirements api failure detail: %s", scraper.name, _read_failure_detail(exc)
        )
        return None


def _read_requirements_from_job_page(
    job: Job, html_downloader: FallbackHtmlDownloader, scraper: Scraper
) -> str | None:
    url = job.get("url")
    if not url:
        return None
    if not _is_allowed_host(url):
        return None
    job_page_download = html_downloader.download_html(url)
    if not job_page_download.html:
        return None
    return scraper.parse_detail(job_page_download.html)


def _is_allowed_host(url: str) -> bool:
    try:
        hostname = urlparse(url).hostname
    except Exception:
        return False
    if not hostname:
        return False
    return hostname.lower() in ALLOWED_URL_HOSTS


def _read_future_result_or_none(future: Future[str | None], site_name: str) -> str | None:
    try:
        return future.result()
    except Exception as exc:
        _LOG.warning(
            "[%s] requirements read crashed (%s)", site_name, _read_short_failure_reason(exc)
        )
        _LOG.debug("[%s] requirements read crash detail: %s", site_name, _read_failure_detail(exc))
        return None


def _read_short_failure_reason(exc: Exception) -> str:
    if isinstance(exc, ApiError):
        return exc.code
    return type(exc).__name__


def _read_failure_detail(exc: Exception) -> str:
    if isinstance(exc, ApiError):
        return exc.detail
    return str(exc)


def _build_filtered_payload(
    jobs: list[Job],
    unfiltered_jobs: _UnfilteredJobsFromApiOrHtml,
    keyword: str,
    fields: frozenset[str],
    max_age_hours: int | None,
    content_filter: dict[str, list[str]],
) -> Payload:
    projected = project_jobs(jobs, fields)
    return {
        "keyword": keyword,
        "fields": sorted(fields),
        "max_age_hours": max_age_hours,
        "filter": _convert_empty_filter_to_none(content_filter),
        "count": len(projected),
        "jobs": projected,
        "source": unfiltered_jobs.source,
        "fallback_reason": unfiltered_jobs.fallback_reason,
    }


def _convert_empty_filter_to_none(
    content_filter: dict[str, list[str]],
) -> dict[str, list[str]] | None:
    if not content_filter:
        return None
    return content_filter


def _build_api_client_for_search(
    build_api_client: Callable[..., Any], api_config: ApiConfig, proxy_url: str | None
) -> Any:
    if api_config.delay_seconds is None:
        return build_api_client(proxy=proxy_url)
    return build_api_client(proxy=proxy_url, delay=api_config.delay_seconds)


def _build_empty_raw_payload(keyword: str, error: str) -> Payload:
    return {"keyword": keyword, "count": 0, "jobs": [], "error": error}
