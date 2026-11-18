from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    keyword_slug,
    resolve_concurrency,
)
from .fetchers import (
    CloudscraperFetcher,
    CurlCffiFetcher,
    FetchChain,
    PlaywrightFetcher,
)
from .log import get_logger, redact_proxy_url
from .sites import SCRAPERS, Scraper
from .sites._dates import parse_to_iso
from .sites._filter import filter_reason, project_jobs
from .sites._location import refresh_index
from .types import CANONICAL_FIELDS, Job

_LOG = get_logger()

KEYWORDS_REQUIRED = "keywords are required"

Payload = dict[str, Any]
PairKey = tuple[str, str]


@dataclass(frozen=True)
class SitePayloads:
    filtered: Payload
    raw: Payload


@dataclass(frozen=True)
class RunResult:
    exit_code: int
    results: Mapping[PairKey, SitePayloads] = field(default_factory=lambda: MappingProxyType({}))
    error: str | None = None

    def get(self, keyword: str, site: str) -> SitePayloads | None:
        return self.results.get((keyword, site))


def _empty_raw(keyword: str, error: str) -> Payload:
    return {"keyword": keyword, "count": 0, "jobs": [], "error": error}


def pair_error(keyword: str, reason: str) -> SitePayloads:
    return SitePayloads(
        filtered={"error": reason, "keyword": keyword, "source": None, "fallback_reason": None},
        raw=_empty_raw(keyword, reason),
    )


def default_fetch_chain(proxy: str | None = None) -> FetchChain:
    return FetchChain(
        [
            CurlCffiFetcher(proxy=proxy),
            CloudscraperFetcher(proxy=proxy),
            PlaywrightFetcher(proxy=proxy),
        ]
    )


def _enrich_jobs(jobs: list[Job], keyword: str) -> None:
    for job in jobs:
        if job.get("matched_keyword") is None:
            job["matched_keyword"] = keyword
        if job.get("posted_at") is None:
            job["posted_at"] = parse_to_iso(job.get("posted_date"))


def _within_max_age(job: Job, cutoff: datetime | None) -> bool:
    if cutoff is None:
        return True
    raw = job.get("posted_at")
    if not isinstance(raw, str):
        return True
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed >= cutoff


def _fetch_requirements(
    jobs: list[Job],
    fields: frozenset[str],
    fetcher: FetchChain,
    scraper: Scraper,
    detail: Callable[[Job], str | None] | None = None,
) -> None:
    if "requirements" not in fields or not jobs or scraper.api_only:
        return

    def _from_page(job: Job) -> str | None:
        url = job.get("url")
        if not url:
            return None
        try:
            host = (urlparse(url).hostname or "").lower()
        except Exception:
            return None
        if host not in ALLOWED_URL_HOSTS:
            return None
        result = fetcher.fetch(url)
        return scraper.parse_detail(result.html) if result.html else None

    def _fetch_one(job: Job) -> str | None:
        existing = job.get("requirements")
        if isinstance(existing, str) and existing.strip():
            return existing
        if detail is not None:
            try:
                text = detail(job)
            except Exception as exc:  # ApiError or a mapping bug: fall back to the job page
                _LOG.debug("[%s] detail api failed for %s: %s", scraper.name, job.get("url"), exc)
                text = None
            if text:
                return text
        return _from_page(job)

    _LOG.info("[%s] fetching requirements for %d job(s)", scraper.name, len(jobs))
    with ThreadPoolExecutor(max_workers=min(4, len(jobs))) as ex:
        futures = {ex.submit(_fetch_one, job): i for i, job in enumerate(jobs)}
        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                jobs[idx]["requirements"] = fut.result()
            except Exception:
                jobs[idx]["requirements"] = None


def _api_failure(keyword: str, reason: str) -> SitePayloads:
    error = f"api failed: {reason}"
    return SitePayloads(
        filtered={
            "error": error,
            "keyword": keyword,
            "source": "api",
            "fallback_reason": None,
        },
        raw=_empty_raw(keyword, error),
    )


def _fetch_failure(
    scraper: Scraper, keyword: str, attempts: list[Payload], fallback_reason: str | None
) -> SitePayloads:
    return SitePayloads(
        filtered={
            "error": "fetch failed",
            "url": scraper.url,
            "keyword": keyword,
            "attempts": attempts,
            "source": "html",
            "fallback_reason": fallback_reason,
        },
        raw=_empty_raw(keyword, "fetch failed"),
    )


def _html_jobs(
    scraper: Scraper,
    fetcher: FetchChain,
    keyword: str,
    label: str,
    fallback_reason: str | None,
) -> list[Job] | SitePayloads:
    _LOG.info("[%s] fetching %s", label, scraper.url)
    result = fetcher.fetch(scraper.url)
    html = result.html
    if not html and scraper.requires_search_html:
        _LOG.error("[%s] FAILED: no html", label)
        attempts = [a.to_dict() for a in result.attempts]
        return _fetch_failure(scraper, keyword, attempts, fallback_reason)

    if html:
        _LOG.info("[%s] fetched search html (%d bytes)", label, len(html))
    else:
        _LOG.info("[%s] no search html (scraper handles fetch internally)", label)
    return scraper.parse(html or "")


def run_one(
    scraper: Scraper,
    fetcher: FetchChain,
    keyword: str,
    fields: frozenset[str],
    max_age_hours: int | None,
    content_filter: dict[str, list[str]],
    *,
    api_search: Callable[[], list[Job]] | None = None,
    api_detail: Callable[[Job], str | None] | None = None,
) -> SitePayloads:
    label = f"{scraper.name}:{keyword_slug(keyword)}"

    jobs: list[Job] | None = None
    source = "html"
    fallback_reason: str | None = None
    if api_search is not None:
        try:
            jobs = api_search()
            source = "api"
            _LOG.info("[%s] api returned %d job(s)", label, len(jobs))
        # fallback_reason is a short code only: it is stored in Mongo, so it must never carry
        # third-party response bodies or exception text (which can include proxy details)
        except ApiError as exc:
            fallback_reason = exc.code
            _LOG.warning("[%s] api failed (%s)", label, exc.code)
            _LOG.debug("[%s] api failure detail: %s", label, exc.detail)
        except Exception as exc:  # unexpected response shape must not kill the pair
            fallback_reason = f"unexpected_error:{type(exc).__name__}"
            _LOG.exception("[%s] api crashed", label)

    if jobs is None and scraper.api_only:
        return _api_failure(keyword, fallback_reason or "api_disabled")

    if jobs is None:
        if fallback_reason is not None:
            _LOG.warning("[%s] falling back to html (%s)", label, fallback_reason)
        html_outcome = _html_jobs(scraper, fetcher, keyword, label, fallback_reason)
        if isinstance(html_outcome, SitePayloads):
            return html_outcome
        jobs = html_outcome

    parsed_count = len(jobs)
    _LOG.info("[%s] parsed %d job(s) via %s", label, parsed_count, source)

    _enrich_jobs(jobs, keyword)

    # snapshot ALL parsed jobs (only the site's query-param filtering applied) BEFORE
    # any Python-level filter/limit/projection. project_jobs builds fresh dicts, so the
    # later in-place requirements enrichment cannot leak back into this raw record.
    raw_jobs = project_jobs(jobs, CANONICAL_FIELDS)
    raw_payload: Payload = {
        "keyword": keyword,
        "fields": sorted(CANONICAL_FIELDS),
        "count": len(raw_jobs),
        "jobs": raw_jobs,
        "source": source,
        "fallback_reason": fallback_reason,
    }
    _LOG.info("[%s] kept %d raw job(s)", label, len(raw_jobs))

    cutoff: datetime | None = None
    if max_age_hours is not None:
        cutoff = datetime.now(UTC) - timedelta(hours=max_age_hours)
        before = len(jobs)
        recent: list[Job] = []
        for job in jobs:
            if _within_max_age(job, cutoff):
                recent.append(job)
            else:
                _LOG.debug(
                    "[%s] drop stale: %r posted_at=%s < cutoff=%s",
                    label,
                    job.get("title"),
                    job.get("posted_at"),
                    cutoff.isoformat(),
                )
        jobs = recent
        _LOG.info(
            "[%s] max_age=%dh cutoff=%s kept %d/%d (dropped %d stale)",
            label,
            max_age_hours,
            cutoff.isoformat(),
            len(jobs),
            before,
            before - len(jobs),
        )

    if content_filter:
        before = len(jobs)
        matched: list[Job] = []
        for job in jobs:
            reason = filter_reason(job, content_filter)
            if reason is None:
                matched.append(job)
            else:
                _LOG.debug("[%s] drop filter: %r %s", label, job.get("title"), reason)
        jobs = matched
        _LOG.info(
            "[%s] filter=%s kept %d/%d (dropped %d)",
            label,
            content_filter,
            len(jobs),
            before,
            before - len(jobs),
        )

    if len(jobs) > scraper.limit:
        _LOG.info("[%s] capping %d job(s) to limit=%d", label, len(jobs), scraper.limit)
        jobs = jobs[: scraper.limit]

    _fetch_requirements(
        jobs, fields, fetcher, scraper, detail=api_detail if source == "api" else None
    )

    projected = project_jobs(jobs, fields)
    filtered_payload: Payload = {
        "keyword": keyword,
        "fields": sorted(fields),
        "max_age_hours": max_age_hours,
        "filter": content_filter or None,
        "count": len(projected),
        "jobs": projected,
        "source": source,
        "fallback_reason": fallback_reason,
    }
    _LOG.info("[%s] done with %d job(s)", label, len(projected))
    return SitePayloads(filtered=filtered_payload, raw=raw_payload)


def build_api_callbacks(
    source_factory: Callable[[Any], ApiSource],
    api_cfg: ApiConfig,
    keyword: str,
    *,
    proxy_url: str | None,
    max_age_hours: int | None,
    limit: int,
    client_factory: Callable[..., Any] = ApiClient,
) -> tuple[Callable[[], list[Job]], Callable[[Job], str | None]]:
    """Search and detail get separate clients: search keeps the site's pace (LinkedIn needs
    4-6s), detail calls for many jobs use a short pause so a run does not take minutes."""
    search_client = (
        client_factory(proxy=proxy_url, delay=api_cfg.delay_seconds)
        if api_cfg.delay_seconds is not None
        else client_factory(proxy=proxy_url)
    )
    search_source = source_factory(search_client)
    detail_source = source_factory(client_factory(proxy=proxy_url, delay=DETAIL_DELAY_SECONDS))
    locations, country_wide = api_cfg.locations, api_cfg.country_wide

    def _search() -> list[Job]:
        return search_all(search_source, keyword, locations, country_wide, max_age_hours, limit)

    return _search, detail_source.detail


def _can_call_api(scraper: Scraper, api_cfg: ApiConfig, name: str) -> bool:
    if not api_cfg.enabled or name not in API_SOURCES:
        return False
    # no locations means no calls: an api-only site would look like "0 jobs found"
    return not scraper.api_only or bool(api_cfg.locations) or api_cfg.country_wide


def _select_targets(config: AppConfig, requested: Iterable[str]) -> list[str]:
    requested_list = list(requested)
    if requested_list:
        return requested_list
    return list(config.enabled_site_names())


def _build_pairs(sites: list[str], keywords: list[str]) -> list[tuple[str, str]]:
    return [(keyword, site) for keyword in keywords for site in sites]


def _site_payloads(
    config: AppConfig, keyword: str, name: str, fetcher: FetchChain, proxy_url: str | None
) -> SitePayloads:
    site_cfg = config.site(name)
    if site_cfg is None:
        _LOG.warning("[runner] '%s' has no entry in the job settings; skipping", name)
        return pair_error(keyword, "skipped: site has no entry in the job settings")
    scraper = SCRAPERS[name](url=site_cfg.url_for(keyword), limit=site_cfg.limit)
    api_search: Callable[[], list[Job]] | None = None
    api_detail: Callable[[Job], str | None] | None = None
    api_cfg = site_cfg.api
    if api_cfg is not None and _can_call_api(scraper, api_cfg, name):
        api_search, api_detail = build_api_callbacks(
            API_SOURCES[name],
            api_cfg,
            keyword,
            proxy_url=proxy_url,
            max_age_hours=site_cfg.max_age_hours,
            limit=site_cfg.limit,
        )
    return run_one(
        scraper,
        fetcher,
        keyword,
        config.fields_for(name),
        site_cfg.max_age_hours,
        site_cfg.filter,
        api_search=api_search,
        api_detail=api_detail,
    )


def _safe_site_payloads(
    config: AppConfig, pair: PairKey, fetcher: FetchChain, proxy_url: str | None
) -> SitePayloads:
    keyword, name = pair
    try:
        return _site_payloads(config, keyword, name, fetcher, proxy_url)
    except Exception as exc:
        _LOG.exception("[%s:%s] pair crashed", name, keyword_slug(keyword))
        return pair_error(keyword, f"crashed: {type(exc).__name__}")


def _run_pairs(
    config: AppConfig, pairs: list[PairKey], fetcher: FetchChain, proxy_url: str | None
) -> dict[PairKey, SitePayloads]:
    workers = max(1, min(resolve_concurrency(), len(pairs)))
    if workers == 1:
        return {pair: _safe_site_payloads(config, pair, fetcher, proxy_url) for pair in pairs}

    _LOG.info(
        "[runner] running %d (keyword,site) pair(s) with concurrency=%d",
        len(pairs),
        workers,
    )
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="scraper") as ex:
        futures = {
            ex.submit(_safe_site_payloads, config, pair, fetcher, proxy_url): pair for pair in pairs
        }
        return {futures[fut]: fut.result() for fut in as_completed(futures)}


def normalize_keywords(keywords: Iterable[str] | None) -> list[str]:
    stripped = (keyword.strip() for keyword in keywords or ())
    return [keyword for keyword in stripped if keyword]


def _selection_error(selected: list[str], keywords: list[str]) -> str | None:
    if not keywords:
        return KEYWORDS_REQUIRED
    if not selected:
        return "no sites selected (none enabled in config and no CLI args)"
    unknown = [name for name in selected if name not in SCRAPERS]
    if unknown:
        return f"unknown sites: {', '.join(unknown)}. available: {', '.join(SCRAPERS)}"
    return None


def run(
    config: AppConfig,
    targets: Iterable[str] = (),
    keywords: Iterable[str] | None = None,
) -> RunResult:
    selected = _select_targets(config, targets)
    keyword_list = normalize_keywords(keywords)
    error = _selection_error(selected, keyword_list)
    if error is not None:
        _LOG.error("[runner] %s", error)
        return RunResult(exit_code=1, error=error)

    pairs = _build_pairs(selected, keyword_list)
    proxy_url = config.proxy.url if config.proxy else None
    if proxy_url:
        _LOG.info("[runner] using proxy: %s", redact_proxy_url(proxy_url))
    fetcher = default_fetch_chain(proxy=proxy_url)

    # Load the wilayah location index fresh from Mongo once, single-threaded, before
    # workers fan out. Reflects current data each run; threads then read it via
    # get_index() during filtering. Degrades to legacy substring if Mongo is absent.
    refresh_index()

    results = _run_pairs(config, pairs, fetcher, proxy_url)
    ordered = {pair: results[pair] for pair in pairs}
    return RunResult(exit_code=0, results=MappingProxyType(ordered))
