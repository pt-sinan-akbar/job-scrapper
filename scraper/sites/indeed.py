from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

from ..api.client import ApiError
from ..log import get_scraper_logger
from ..types import Job, empty_job
from ._markdown import html_to_markdown
from .base import Scraper

_LOG = get_scraper_logger()

_INDEED_API_URL = "https://apis.indeed.com/graphql"
_INDEED_API_KEY = (
    "161092c2017b5bbab13edb12461a62d5a833871e7cad6d9d475304573de67ac8"  # pragma: allowlist secret
)
_INDEED_API_HEADERS = {
    "Host": "apis.indeed.com",
    "content-type": "application/json",
    "indeed-api-key": _INDEED_API_KEY,
    "accept": "application/json",
    "indeed-locale": "en-US",
    "accept-language": "en-US,en;q=0.9",
    "user-agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6_1 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Indeed App 193.1"
    ),
    "indeed-app-info": ("appv=193.1; appid=com.indeed.jobsearch; osv=16.6.1; os=ios; dtype=phone"),
    "indeed-co": "ID",
}

_DEFAULT_LOCATION = "Indonesia"
_DEFAULT_RADIUS_MILES = 50

_GRAPHQL_QUERY_TEMPLATE = """
query GetJobData {{
  jobSearch(
    what: "{what}"
    location: {{where: "{where}", radius: {radius}, radiusUnit: MILES}}
    limit: {limit}
  ) {{
    results {{
      job {{
        key
        title
        datePublished
        dateOnIndeed
        description {{ html }}
        location {{ city formatted {{ long short }} }}
        employer {{ name }}
        compensation {{
          estimated {{
            currencyCode
            baseSalary {{
              unitOfWork
              range {{
                ... on Range {{ min max }}
              }}
            }}
          }}
        }}
      }}
    }}
  }}
}}
"""


def _extract_search_params(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    keyword = (qs.get("q") or [""])[0].replace("+", " ").strip()
    where = (qs.get("l") or [_DEFAULT_LOCATION])[0].strip() or _DEFAULT_LOCATION
    return keyword, where


def _format_salary(compensation: dict | None) -> str | None:
    if not isinstance(compensation, dict):
        return None
    estimated = compensation.get("estimated") or {}
    if not isinstance(estimated, dict):
        return None
    base = estimated.get("baseSalary") or {}
    if not isinstance(base, dict):
        return None
    rng = base.get("range") or {}
    if not isinstance(rng, dict):
        return None
    currency = estimated.get("currencyCode") or ""
    unit = base.get("unitOfWork") or ""
    lo = rng.get("min")
    hi = rng.get("max")
    if lo is not None and hi is not None:
        return f"{currency} {lo}-{hi} {unit}".strip()
    if lo is not None:
        return f"{currency} {lo}+ {unit}".strip()
    return None


def _iso_from_millis(value: object) -> str | None:
    if not isinstance(value, int | float) or value <= 0:
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=UTC).isoformat()
    except (ValueError, OSError):
        return None


def _country_from_url(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    # id.indeed.com → "id", uk.indeed.com → "uk", indeed.com → "www"
    if host.endswith(".indeed.com"):
        prefix = host.split(".indeed.com", 1)[0]
        return prefix or "www"
    return "id"


def _fetch_jobs_from_api(keyword: str, where: str, limit: int) -> list[dict]:
    if not keyword:
        _LOG.warning("[indeed-api] empty keyword; nothing to query")
        return []
    try:
        from curl_cffi import requests as cffi_requests  # type: ignore[attr-defined]
    except Exception as exc:
        _LOG.error("[indeed-api] curl_cffi missing: %s", exc)
        raise ApiError("not_installed", f"{type(exc).__name__}: {exc}") from exc

    query = _GRAPHQL_QUERY_TEMPLATE.format(
        what=keyword.replace('"', '\\"'),
        where=where.replace('"', '\\"'),
        radius=_DEFAULT_RADIUS_MILES,
        limit=max(1, min(limit, 100)),
    )
    _LOG.info("[indeed-api] POST %s keyword=%r where=%r", _INDEED_API_URL, keyword, where)
    try:
        response = cffi_requests.post(
            _INDEED_API_URL,
            json={"query": query},
            headers=_INDEED_API_HEADERS,
            impersonate="chrome131",
            timeout=30,
        )
    except Exception as exc:
        _LOG.error("[indeed-api] POST error: %s", type(exc).__name__)
        _LOG.debug("[indeed-api] POST error detail: %s", exc)
        raise ApiError("runtime_error", f"{type(exc).__name__}: {exc}") from exc

    if response.status_code != 200:
        _LOG.warning("[indeed-api] status=%d", response.status_code)
        _LOG.debug("[indeed-api] response body: %s", response.text[:200])
        raise ApiError(f"http_{response.status_code}", response.text[:200])
    try:
        payload = response.json()
    except ValueError as exc:
        _LOG.error("[indeed-api] non-JSON response: %s", exc)
        raise ApiError("non_json", str(exc)) from exc
    graphql_errors = payload.get("errors")
    if graphql_errors:
        _LOG.warning("[indeed-api] response has graphql errors")
        _LOG.debug("[indeed-api] graphql errors: %s", graphql_errors)
    results = (payload.get("data") or {}).get("jobSearch", {}).get("results") or []
    if graphql_errors and not results:
        raise ApiError("graphql_error", str(graphql_errors)[:200])
    jobs: list[dict] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        job = item.get("job")
        if isinstance(job, dict):
            jobs.append(job)
    return jobs


class IndeedScraper(Scraper):
    name = "indeed"
    requires_search_html = False

    def parse(self, html: str) -> list[Job]:
        keyword, where = _extract_search_params(self.url)
        country = _country_from_url(self.url)
        jobs_data = _fetch_jobs_from_api(keyword, where, self.limit)
        _LOG.info(
            "[indeed-api] keyword=%r where=%r returned %d job(s)",
            keyword,
            where,
            len(jobs_data),
        )

        results: list[Job] = []
        seen: set[str] = set()
        for entry in jobs_data:
            if not isinstance(entry, dict):
                continue
            title = entry.get("title")
            employer = entry.get("employer") or {}
            company = employer.get("name") if isinstance(employer, dict) else None
            if not title or not company:
                continue
            jk = entry.get("key")
            url = f"https://{country}.indeed.com/viewjob?jk={jk}" if jk else None
            seen_key = url or f"{title}|{company}"
            if seen_key in seen:
                continue
            seen.add(seen_key)

            location_node = entry.get("location") or {}
            formatted = (
                location_node.get("formatted") if isinstance(location_node, dict) else None
            ) or {}
            location = (
                formatted.get("long")
                or formatted.get("short")
                or (location_node.get("city") if isinstance(location_node, dict) else None)
            )

            posted_at = _iso_from_millis(entry.get("datePublished"))
            description = html_to_markdown(
                (entry.get("description") or {}).get("html")
                if isinstance(entry.get("description"), dict)
                else None
            )

            job = empty_job(self.name, title, company)
            job["location"] = location
            job["url"] = url
            job["job_id"] = str(jk) if jk else None
            job["salary"] = _format_salary(entry.get("compensation"))
            job["posted_at"] = posted_at
            job["posted_date"] = posted_at
            job["requirements"] = description
            results.append(job)
            if len(results) >= self.limit:
                break
        return results
