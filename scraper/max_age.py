from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

HOURS_PER_DAY = 24


@dataclass(frozen=True)
class MaxAgeOption:
    value: int
    label: str


MAX_AGE_OPTIONS: tuple[MaxAgeOption, ...] = (
    MaxAgeOption(value=72, label="3 days ago"),
    MaxAgeOption(value=168, label="One week ago"),
    MaxAgeOption(value=720, label="One month ago"),
)


def compute_posted_at_cutoff(max_age_hours: int | None, now: datetime) -> datetime | None:
    if max_age_hours is None:
        return None
    max_age_days = _round_hours_up_to_days(max_age_hours)
    today_midnight = _find_utc_midnight(now)
    return today_midnight - timedelta(days=max_age_days)


def list_max_age_options() -> list[dict[str, Any]]:
    max_age_options: list[dict[str, Any]] = []
    for max_age_option in MAX_AGE_OPTIONS:
        max_age_options.append({"value": max_age_option.value, "label": max_age_option.label})
    return max_age_options


def is_max_age_option(max_age_hours: int) -> bool:
    return max_age_hours in _list_max_age_values()


def build_unknown_max_age_message(max_age_hours: int) -> str:
    allowed_value_labels: list[str] = []
    for max_age_value in _list_max_age_values():
        allowed_value_labels.append(str(max_age_value))
    allowed_values = ", ".join(allowed_value_labels)
    return f"unknown max_age_hours: {max_age_hours}. allowed: {allowed_values}"


def _round_hours_up_to_days(max_age_hours: int) -> int:
    return math.ceil(max_age_hours / HOURS_PER_DAY)


def _find_utc_midnight(moment: datetime) -> datetime:
    utc_moment = moment.astimezone(UTC)
    return datetime(utc_moment.year, utc_moment.month, utc_moment.day, tzinfo=UTC)


def _list_max_age_values() -> list[int]:
    max_age_values: list[int] = []
    for max_age_option in MAX_AGE_OPTIONS:
        max_age_values.append(max_age_option.value)
    return max_age_values
