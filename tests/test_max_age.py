from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from scraper.max_age import (
    build_unknown_max_age_message,
    compute_posted_at_cutoff,
    is_max_age_option,
    list_max_age_options,
)

MORNING_NOW = datetime(2026, 11, 22, 8, 56, tzinfo=UTC)


@pytest.mark.parametrize(
    ("max_age_hours", "expected_cutoff"),
    [
        (72, datetime(2026, 11, 19, tzinfo=UTC)),
        (36, datetime(2026, 11, 20, tzinfo=UTC)),
        (1, datetime(2026, 11, 21, tzinfo=UTC)),
        (24, datetime(2026, 11, 21, tzinfo=UTC)),
        (168, datetime(2026, 11, 15, tzinfo=UTC)),
    ],
)
def test_cutoff_is_midnight_utc_of_today_minus_the_hours_rounded_up_to_days(
    max_age_hours: int, expected_cutoff: datetime
):
    assert compute_posted_at_cutoff(max_age_hours, MORNING_NOW) == expected_cutoff


def test_no_max_age_means_no_cutoff():
    assert compute_posted_at_cutoff(None, MORNING_NOW) is None


def test_cutoff_uses_the_utc_day_of_a_now_given_in_another_timezone():
    jakarta_now = datetime(2026, 11, 22, 3, 0, tzinfo=timezone(timedelta(hours=7)))

    assert compute_posted_at_cutoff(72, jakarta_now) == datetime(2026, 11, 18, tzinfo=UTC)


def test_max_age_options_have_values_and_labels():
    assert list_max_age_options() == [
        {"value": 72, "label": "3 days ago"},
        {"value": 168, "label": "One week ago"},
        {"value": 720, "label": "One month ago"},
    ]


@pytest.mark.parametrize("max_age_hours", [72, 168, 720])
def test_listed_values_are_max_age_options(max_age_hours: int):
    assert is_max_age_option(max_age_hours) is True


@pytest.mark.parametrize("max_age_hours", [0, 24, 48, 73, 721])
def test_other_values_are_not_max_age_options(max_age_hours: int):
    assert is_max_age_option(max_age_hours) is False


def test_unknown_max_age_message_lists_the_allowed_values():
    assert build_unknown_max_age_message(48) == ("unknown max_age_hours: 48. allowed: 72, 168, 720")
