from __future__ import annotations

from typing import Any

from ..types import Job


def pick_allowed_fields_from_jobs(
    jobs: list[Job], allowed_fields: frozenset[str]
) -> list[dict[str, Any]]:
    jobs_with_allowed_fields: list[dict[str, Any]] = []
    for job in jobs:
        jobs_with_allowed_fields.append(_pick_allowed_fields_from_job(job, allowed_fields))
    return jobs_with_allowed_fields


def _pick_allowed_fields_from_job(job: Job, allowed_fields: frozenset[str]) -> dict[str, Any]:
    allowed_field_values: dict[str, Any] = {}
    for field_name, field_value in job.items():
        if field_name in allowed_fields:
            allowed_field_values[field_name] = field_value
    return allowed_field_values
