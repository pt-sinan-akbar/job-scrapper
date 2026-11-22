from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol

from ..types import Job
from .location_search_plan import LocationSearchPlan


class ApiSource(Protocol):
    name: str
    # value passed as `location` for the country-wide call (None = no location param)
    country_location: str | None

    def search(
        self, keyword: str, location: str | None, max_age_hours: int | None, limit: int
    ) -> list[Job]: ...

    def detail(self, job: Job) -> str | None: ...


def _dedup_key(job: Job) -> tuple[str, ...]:
    if job.get("job_id"):
        return ("id", str(job["job_id"]))
    if job.get("url"):
        return ("url", str(job["url"]))
    return ("tc", job["title"], job["company"])


def dedup_jobs(jobs: Iterable[Job]) -> list[Job]:
    seen: set[tuple[str, ...]] = set()
    unique: list[Job] = []
    for job in jobs:
        key = _dedup_key(job)
        if key in seen:
            continue
        seen.add(key)
        unique.append(job)
    return unique


def search_all(
    source: ApiSource,
    keyword: str,
    location_search_plan: LocationSearchPlan,
    max_age_hours: int | None,
    limit: int,
) -> list[Job]:
    job_streams: list[list[Job]] = []
    for city_value in location_search_plan.city_values:
        job_streams.append(source.search(keyword, city_value, max_age_hours, limit))
    if location_search_plan.is_country_wide:
        job_streams.append(source.search(keyword, source.country_location, max_age_hours, limit))
    return dedup_jobs(interleave_job_streams_round_robin(job_streams))


def interleave_job_streams_round_robin[StreamEntry](
    job_streams: Sequence[Sequence[StreamEntry]],
) -> list[StreamEntry]:
    longest_stream_length = 0
    for job_stream in job_streams:
        longest_stream_length = max(longest_stream_length, len(job_stream))
    interleaved_entries: list[StreamEntry] = []
    for position_in_stream in range(longest_stream_length):
        for job_stream in job_streams:
            if position_in_stream < len(job_stream):
                interleaved_entries.append(job_stream[position_in_stream])
    return interleaved_entries
