from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest
import yaml

from scraper.api.location_search_plan import (
    LOCATION_MAPPING_PATH,
    LocationSearchPlan,
    build_location_search_plan,
    build_unknown_location_message,
    find_filter_location_option,
    is_country_location_picked,
    list_filter_location_options,
    read_location_mapping,
)
from tests.log_lines import list_log_lines_containing

REPO_ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = REPO_ROOT / "seeds" / "job_settings.yaml"
CITY_LABELS = ["Jakarta", "Tangerang", "Tangerang Selatan", "Bandung", "Bekasi"]
ALL_LABELS = [*CITY_LABELS, "Indonesia"]
SITES_WITH_CITY_VALUES = ("jobstreet", "glints", "linkedin", "indeed")
COUNTRY_WIDE_ONLY_PLAN = LocationSearchPlan(city_values=(), is_country_wide=True)


def test_options_list_the_cities_first_then_the_country():
    assert list_filter_location_options() == ALL_LABELS


def test_mapping_file_sits_next_to_the_module_and_has_no_comments():
    mapping_text = LOCATION_MAPPING_PATH.read_text()

    assert LOCATION_MAPPING_PATH == REPO_ROOT / "scraper" / "api" / "location_mapping.yaml"
    assert "#" not in mapping_text


def test_mapping_gives_every_city_a_value_on_every_listed_site():
    location_mapping = read_location_mapping()

    assert set(location_mapping.city_values_by_site) == set(SITES_WITH_CITY_VALUES)
    for site_name in SITES_WITH_CITY_VALUES:
        assert list(location_mapping.city_values_by_site[site_name]) == [
            city_label.lower() for city_label in CITY_LABELS
        ]


def test_mapping_is_read_from_disk_only_once():
    assert read_location_mapping() is read_location_mapping()


def test_every_seed_filter_location_is_a_known_option():
    seed_sites = yaml.safe_load(SEED_PATH.read_text())["sites"]

    for site_name in SITES_WITH_CITY_VALUES:
        assert seed_sites[site_name]["filter"]["location"] == ALL_LABELS


def test_plan_has_one_value_per_picked_city_in_picked_order():
    plan = build_location_search_plan("jobstreet", ["bandung", "jakarta"])

    assert plan == LocationSearchPlan(
        city_values=("Bandung Jawa Barat", "Jakarta Raya"), is_country_wide=False
    )


def test_plan_matches_filter_values_ignoring_case_and_outer_spaces():
    plan = build_location_search_plan("indeed", [" Tangerang SELATAN ", "INDONESIA"])

    assert plan == LocationSearchPlan(city_values=("Tangerang",), is_country_wide=True)


def test_plan_is_country_wide_when_indonesia_is_picked():
    plan = build_location_search_plan("glints", ["jakarta", "indonesia"])

    assert plan == LocationSearchPlan(
        city_values=("78d63064-78a1-4577-8516-036a6c5e903e",), is_country_wide=True
    )


def test_plan_with_only_indonesia_has_no_city_values():
    assert build_location_search_plan("jobstreet", ["indonesia"]) == COUNTRY_WIDE_ONLY_PLAN


def test_plan_sends_the_same_city_value_only_once():
    plan = build_location_search_plan("linkedin", ["jakarta", "tangerang", "bandung", "bekasi"])

    assert plan.city_values == ("Jakarta, Indonesia", "Bandung, Indonesia")
    assert plan.is_country_wide is False


def test_empty_filter_acts_like_indonesia():
    assert build_location_search_plan("jobstreet", []) == COUNTRY_WIDE_ONLY_PLAN


def test_site_without_a_mapping_gets_one_request_with_no_location():
    assert build_location_search_plan("upwork", ["jakarta"]) == COUNTRY_WIDE_ONLY_PLAN
    assert build_location_search_plan("upwork", []) == COUNTRY_WIDE_ONLY_PLAN


def test_picked_location_without_a_value_for_the_site_is_skipped_with_a_log_line(
    scraper_log_records: pytest.LogCaptureFixture,
):
    plan = build_location_search_plan("jobstreet", ["surabaya", "bekasi"])

    assert plan == LocationSearchPlan(city_values=("Bekasi Jawa Barat",), is_country_wide=False)
    assert list_log_lines_containing(scraper_log_records.messages, "surabaya") != []


def test_plan_with_only_unmapped_locations_has_no_request():
    plan = build_location_search_plan("jobstreet", ["surabaya"])

    assert plan.has_any_request() is False


@pytest.mark.parametrize(
    "plan",
    [
        LocationSearchPlan(city_values=("Jakarta Raya",), is_country_wide=False),
        LocationSearchPlan(city_values=(), is_country_wide=True),
    ],
)
def test_plan_with_a_city_value_or_the_country_has_a_request(plan: LocationSearchPlan):
    assert plan.has_any_request() is True


def test_plan_is_immutable():
    with pytest.raises(dataclasses.FrozenInstanceError):
        dataclasses.replace(COUNTRY_WIDE_ONLY_PLAN).__setattr__("is_country_wide", False)


@pytest.mark.parametrize(
    ("filter_locations", "expected"),
    [
        (["jakarta", "Indonesia"], True),
        ([" INDONESIA "], True),
        (["jakarta"], False),
        ([], False),
    ],
)
def test_country_location_is_picked_ignoring_case(filter_locations: list[str], expected: bool):
    assert is_country_location_picked(filter_locations) is expected


@pytest.mark.parametrize(
    ("passed_location", "expected_option"),
    [
        ("jakarta", "Jakarta"),
        ("JAKARTA", "Jakarta"),
        ("  tangerang selatan ", "Tangerang Selatan"),
        ("indonesia", "Indonesia"),
    ],
)
def test_find_option_matches_a_listed_location_case_insensitively(
    passed_location: str, expected_option: str
):
    assert find_filter_location_option(passed_location) == expected_option


@pytest.mark.parametrize("passed_location", ["surabaya", "", "   ", "jakarta raya"])
def test_find_option_gives_none_for_an_unlisted_location(passed_location: str):
    assert find_filter_location_option(passed_location) is None


def test_unknown_location_message_names_the_location_and_every_option():
    assert build_unknown_location_message("surabaya") == (
        "unknown location: surabaya. allowed: Jakarta, Tangerang, "
        "Tangerang Selatan, Bandung, Bekasi, Indonesia"
    )
