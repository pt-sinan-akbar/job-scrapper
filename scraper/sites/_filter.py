from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from ..api.location_search_plan import is_country_location_picked
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
_LOCATION_FIELD = "location"
_has_warned_about_missing_location_index = False


class JobDropKind(StrEnum):
    STALE = "stale"
    FILTER = "filter"


@dataclass(frozen=True)
class JobDropReason:
    kind: JobDropKind
    description: str


@dataclass(frozen=True)
class _PickedLocationTerms:
    region_code_prefixes: frozenset[str]
    non_region_terms: tuple[str, ...]


def find_job_drop_reason(
    job: Job, content_filter: dict[str, list[str]], posted_at_cutoff: datetime | None
) -> JobDropReason | None:
    stale_drop_reason = _find_stale_drop_reason(job, posted_at_cutoff)
    if stale_drop_reason is not None:
        return stale_drop_reason

    content_filter_failure = find_content_filter_failure(job, content_filter)
    if content_filter_failure is None:
        return None
    return JobDropReason(JobDropKind.FILTER, content_filter_failure)


def find_content_filter_failure(job: Job, content_filter: dict[str, list[str]]) -> str | None:
    for field_name, expected_values in content_filter.items():
        field_failure = _find_field_failure(job, field_name, expected_values)
        if field_failure is not None:
            return field_failure
    return None


def _find_stale_drop_reason(job: Job, posted_at_cutoff: datetime | None) -> JobDropReason | None:
    if posted_at_cutoff is None:
        return None
    if _is_posted_at_or_after_cutoff(job, posted_at_cutoff):
        return None
    description = f"posted_at={job.get('posted_at')} < cutoff={posted_at_cutoff.isoformat()}"
    return JobDropReason(JobDropKind.STALE, description)


def _is_posted_at_or_after_cutoff(job: Job, posted_at_cutoff: datetime) -> bool:
    posted_at = _read_posted_at_as_utc(job)
    if posted_at is None:
        return True
    return posted_at >= posted_at_cutoff


def _read_posted_at_as_utc(job: Job) -> datetime | None:
    posted_at_text = job.get("posted_at")
    if not isinstance(posted_at_text, str):
        return None
    try:
        posted_at = datetime.fromisoformat(posted_at_text)
    except ValueError:
        return None
    if posted_at.tzinfo is None:
        return posted_at.replace(tzinfo=UTC)
    return posted_at


def _find_field_failure(job: Job, field_name: str, expected_values: list[str]) -> str | None:
    if not expected_values:
        return None
    field_value = job.get(field_name)
    if field_value is None:
        return None

    field_text = str(field_value)
    if field_name == _LOCATION_FIELD:
        return _find_location_failure(field_text, expected_values)
    return _find_substring_failure(field_name, field_text, expected_values)


def _find_substring_failure(
    field_name: str, field_text: str, expected_values: list[str]
) -> str | None:
    lowercase_field_text = field_text.strip().lower()
    matching_expected_value = _find_expected_value_inside_text(
        lowercase_field_text, expected_values
    )
    if matching_expected_value is not None:
        return None
    return f"{field_name}={field_text!r} not in {expected_values}"


def _find_expected_value_inside_text(
    lowercase_field_text: str, expected_values: list[str]
) -> str | None:
    for expected_value in expected_values:
        if expected_value in lowercase_field_text:
            return expected_value
    return None


def _find_location_failure(location_text: str, expected_locations: list[str]) -> str | None:
    if _is_blank(location_text):
        return None

    location_index = get_location_index()
    if location_index is None:
        return _find_location_failure_by_substring(location_text, expected_locations)
    return _find_location_failure_by_region(location_text, expected_locations, location_index)


def _is_blank(text: str) -> bool:
    return not text.strip()


def _find_location_failure_by_substring(
    location_text: str, expected_locations: list[str]
) -> str | None:
    _warn_once_about_missing_location_index()
    return _find_substring_failure(_LOCATION_FIELD, location_text, expected_locations)


def _warn_once_about_missing_location_index() -> None:
    global _has_warned_about_missing_location_index
    if _has_warned_about_missing_location_index:
        return
    _has_warned_about_missing_location_index = True
    _LOG.warning("[filter] wilayah index unavailable; location filter using legacy substring")


def _find_location_failure_by_region(
    location_text: str, expected_locations: list[str], location_index: WilayahIndex
) -> str | None:
    picked_location_terms = _split_picked_locations_into_regions_and_other_terms(
        expected_locations, location_index
    )
    job_region_codes = find_candidate_region_codes(location_text, location_index)
    if is_any_region_code_under_prefixes(
        job_region_codes, picked_location_terms.region_code_prefixes
    ):
        return None
    if job_region_codes:
        return _find_failure_for_region_outside_picked_regions(location_text, expected_locations)
    return _find_failure_for_unresolved_location(
        location_text, expected_locations, picked_location_terms.non_region_terms
    )


def _split_picked_locations_into_regions_and_other_terms(
    expected_locations: list[str], location_index: WilayahIndex
) -> _PickedLocationTerms:
    region_code_prefixes: set[str] = set()
    non_region_terms: list[str] = []
    for expected_location in expected_locations:
        prefixes_of_location = find_region_code_prefixes_for_term(
            expected_location, location_index.province_and_city_entries
        )
        if prefixes_of_location:
            region_code_prefixes.update(prefixes_of_location)
        else:
            non_region_terms.append(normalize_location_text(expected_location))
    return _PickedLocationTerms(frozenset(region_code_prefixes), tuple(non_region_terms))


def _find_failure_for_region_outside_picked_regions(
    location_text: str, expected_locations: list[str]
) -> str | None:
    if is_country_location_picked(expected_locations):
        return None
    return f"location={location_text!r} resolved out of scope, not in {expected_locations}"


def _find_failure_for_unresolved_location(
    location_text: str, expected_locations: list[str], non_region_terms: tuple[str, ...]
) -> str | None:
    if _is_any_term_a_location_segment(location_text, non_region_terms):
        return None
    return f"location={location_text!r} unresolved, not in {expected_locations}"


def _is_any_term_a_location_segment(location_text: str, non_region_terms: tuple[str, ...]) -> bool:
    normalized_location_text = normalize_location_text(location_text)
    location_segments = set(split_location_segments(normalized_location_text))
    matching_terms = location_segments.intersection(non_region_terms)
    return len(matching_terms) > 0
