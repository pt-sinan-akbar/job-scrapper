from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.schemas.scrapes import StartScrapeRequest

BASE_REQUEST = {"keywords": ["AI Engineer"], "sites": ["glints"]}


@pytest.mark.parametrize(
    ("passed_location", "expected_location"),
    [
        ("jakarta", "Jakarta"),
        ("tangerang selatan", "Tangerang Selatan"),
        ("indonesia", "Indonesia"),
        ("BANDUNG", "Bandung"),
    ],
)
def test_location_matches_a_scraper_option_case_insensitively(
    passed_location: str, expected_location: str
):
    start_request = StartScrapeRequest.model_validate({**BASE_REQUEST, "location": passed_location})

    assert start_request.location == expected_location


def test_location_is_optional():
    start_request = StartScrapeRequest.model_validate(BASE_REQUEST)

    assert start_request.location is None


def test_null_location_means_no_location():
    start_request = StartScrapeRequest.model_validate({**BASE_REQUEST, "location": None})

    assert start_request.location is None


def test_unknown_location_is_rejected_with_the_allowed_options():
    with pytest.raises(ValidationError) as validation_error:
        StartScrapeRequest.model_validate({**BASE_REQUEST, "location": "surabaya"})

    error_message = str(validation_error.value)
    assert "unknown location: surabaya" in error_message
    assert "Jakarta, Tangerang, Tangerang Selatan, Bandung, Bekasi, Indonesia" in error_message


def test_other_extra_fields_are_still_rejected():
    with pytest.raises(ValidationError):
        StartScrapeRequest.model_validate({**BASE_REQUEST, "city": "jakarta"})


@pytest.mark.parametrize("max_age_hours", [72, 168, 720])
def test_listed_max_age_is_accepted(max_age_hours: int):
    start_request = StartScrapeRequest.model_validate(
        {**BASE_REQUEST, "max_age_hours": max_age_hours}
    )

    assert start_request.max_age_hours == max_age_hours


def test_max_age_is_optional():
    start_request = StartScrapeRequest.model_validate(BASE_REQUEST)

    assert start_request.max_age_hours is None


def test_null_max_age_means_the_saved_max_age():
    start_request = StartScrapeRequest.model_validate({**BASE_REQUEST, "max_age_hours": None})

    assert start_request.max_age_hours is None


@pytest.mark.parametrize("max_age_hours", [0, 24, 48, 73, 721, -72])
def test_unlisted_max_age_is_rejected_with_the_allowed_values(max_age_hours: int):
    with pytest.raises(ValidationError) as validation_error:
        StartScrapeRequest.model_validate({**BASE_REQUEST, "max_age_hours": max_age_hours})

    assert f"unknown max_age_hours: {max_age_hours}. allowed: 72, 168, 720" in str(
        validation_error.value
    )


def test_non_number_max_age_is_rejected():
    with pytest.raises(ValidationError):
        StartScrapeRequest.model_validate({**BASE_REQUEST, "max_age_hours": "a week"})
