from __future__ import annotations

from typing import Any

from ..log import get_scraper_logger
from ..types import Job
from ._location import (
    WilayahIndex,
    find_candidate_region_codes,
    find_region_code_prefixes_for_term,
    get_location_index,
    is_any_region_code_under_prefixes,
    normalize_location_text,
    split_location_segments,
)

_LOG = get_scraper_logger()
_WARNED_LEGACY = False


def project_job(job: Job, allowed: frozenset[str]) -> dict[str, Any]:
    return {key: value for key, value in job.items() if key in allowed}


def project_jobs(jobs: list[Job], allowed: frozenset[str]) -> list[dict[str, Any]]:
    return [project_job(job, allowed) for job in jobs]


def _warn_legacy_once() -> None:
    global _WARNED_LEGACY
    if not _WARNED_LEGACY:
        _WARNED_LEGACY = True
        _LOG.warning("[filter] wilayah index unavailable; location filter using legacy substring")


def _partition_terms(
    expected_values: list[str], index: WilayahIndex
) -> tuple[frozenset[str], tuple[str, ...]]:
    prefixes: set[str] = set()
    literals: list[str] = []
    for term in expected_values:
        found = find_region_code_prefixes_for_term(term, index.province_and_city_entries)
        if found:
            prefixes |= found
        else:
            literals.append(normalize_location_text(term))
    return frozenset(prefixes), tuple(literals)


def _location_reason(raw: str, actual_lower: str, expected_values: list[str]) -> str | None:
    if not actual_lower:
        return None  # blank location: keep (mirrors null handling)

    index = get_location_index()
    if index is None:  # genuine load failure -> legacy substring
        _warn_legacy_once()
        if any(e in actual_lower for e in expected_values):
            return None
        return f"location={raw!r} not in {expected_values}"

    prefixes, literals = _partition_terms(expected_values, index)
    candidate_region_codes = find_candidate_region_codes(raw, index)
    if is_any_region_code_under_prefixes(candidate_region_codes, prefixes):
        return None  # (a) under an in-scope region
    if candidate_region_codes:
        return f"location={raw!r} resolved out of scope, not in {expected_values}"  # (b)
    location_segments = set(split_location_segments(normalize_location_text(raw)))
    if any(literal_term in location_segments for literal_term in literals):
        return None  # (c) nationwide/remote literal
    return f"location={raw!r} unresolved, not in {expected_values}"


def filter_reason(job: Job, filter_: dict[str, list[str]]) -> str | None:
    """Return None if the job passes, else a short reason for the first failing key.

    The ``location`` key uses the wilayah hierarchy resolver; all other keys keep
    case-insensitive substring matching. Empty candidate lists and null/blank fields
    are skipped (the job is kept).
    """
    for key, expected_values in filter_.items():
        if not expected_values:
            continue
        actual = job.get(key)
        if actual is None:
            continue
        if not isinstance(actual, str):
            actual = str(actual)
        actual_lower = actual.strip().lower()

        if key == "location":
            reason = _location_reason(actual, actual_lower, expected_values)
        elif any(expected in actual_lower for expected in expected_values):
            reason = None
        else:
            reason = f"{key}={actual!r} not in {expected_values}"

        if reason is not None:
            return reason
    return None


def matches_filter(job: Job, filter_: dict[str, list[str]]) -> bool:
    return filter_reason(job, filter_) is None


def apply_filter(jobs: list[Job], filter_: dict[str, list[str]]) -> list[Job]:
    if not filter_:
        return jobs
    return [job for job in jobs if matches_filter(job, filter_)]
