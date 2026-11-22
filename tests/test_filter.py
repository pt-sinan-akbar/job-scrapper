from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import patch

import pytest

import scraper.sites._filter as filt
import scraper.sites._location as loc
from scraper.sites._filter import JobDropKind, find_content_filter_failure, find_job_drop_reason
from scraper.sites._location import build_wilayah_index
from scraper.types import Job, empty_job
from tests.log_lines import list_log_lines_containing, list_warning_or_above_log_lines
from tests.wilayah_rows import WILAYAH_ROWS


def _job(location: str | None):
    job = empty_job("glints", "Data Analyst", "Acme")
    job["location"] = location
    return job


def test_content_filter_failure_none_when_match():
    assert find_content_filter_failure(_job("Jakarta Selatan"), {"location": ["jakarta"]}) is None


def test_content_filter_failure_reports_failing_key_and_value():
    reason = find_content_filter_failure(_job("Surabaya"), {"location": ["jakarta", "bekasi"]})
    assert reason is not None
    assert "location" in reason
    assert "Surabaya" in reason


def test_content_filter_failure_skips_null_field():
    # Missing/None field is kept (conservative) — no reason to drop.
    assert find_content_filter_failure(_job(None), {"location": ["jakarta"]}) is None


def test_content_filter_failure_skips_empty_candidate_list():
    assert find_content_filter_failure(_job("Surabaya"), {"location": []}) is None


def test_content_filter_failure_drops_a_location_outside_the_filter():
    job = _job("Surabaya")
    assert find_content_filter_failure(job, {"location": ["jakarta"]}) is not None


# --- hierarchy-aware location dispatch (patch the wilayah index) ---

JKT = {"location": ["jakarta", "tangerang", "bandung", "bekasi", "indonesia"]}
CITIES_ONLY = {"location": ["jakarta", "tangerang", "bandung", "bekasi"]}


def _with_index(rows=WILAYAH_ROWS):
    return patch.object(filt, "get_location_index", return_value=build_wilayah_index(rows))


def test_district_cakung_kept():
    with _with_index():
        assert filt.find_content_filter_failure(_job("Cakung"), JKT) is None


def test_district_tanjung_priok_kept():
    with _with_index():
        assert filt.find_content_filter_failure(_job("Tanjung Priok"), JKT) is None


def test_area_dki_jakarta_kept():
    with _with_index():
        assert filt.find_content_filter_failure(_job("Area DKI Jakarta"), JKT) is None


def test_jakarta_raya_alias_kept():
    with _with_index():
        assert filt.find_content_filter_failure(_job("Jakarta Raya"), JKT) is None


def test_jakarta_raya_indonesia_compound_kept():
    with _with_index():
        assert filt.find_content_filter_failure(_job("Jakarta Raya, Indonesia"), JKT) is None


def test_indonesia_literal_kept():
    with _with_index():
        assert filt.find_content_filter_failure(_job("Indonesia"), JKT) is None


def test_surabaya_indonesia_dropped_when_only_cities_are_picked():
    with _with_index():
        assert (
            filt.find_content_filter_failure(_job("Surabaya, Indonesia"), CITIES_ONLY) is not None
        )


def test_jakarta_baru_dropped():  # Maluku village not in index -> unresolved -> drop
    with _with_index():
        assert filt.find_content_filter_failure(_job("Jakarta Baru"), JKT) is not None


def test_surabaya_dropped_when_only_cities_are_picked():
    with _with_index():
        assert filt.find_content_filter_failure(_job("Surabaya"), CITIES_ONLY) is not None


def test_yogyakarta_dropped_when_only_cities_are_picked():
    with _with_index():
        assert (
            filt.find_content_filter_failure(_job("Yogyakarta dan Sekitarnya"), CITIES_ONLY)
            is not None
        )


def test_picked_city_still_kept_when_only_cities_are_picked():
    with _with_index():
        assert filt.find_content_filter_failure(_job("Cakung"), CITIES_ONLY) is None
        assert filt.find_content_filter_failure(_job("Kabupaten Bandung"), CITIES_ONLY) is None


def test_indonesia_literal_dropped_when_only_cities_are_picked():
    with _with_index():
        assert filt.find_content_filter_failure(_job("Indonesia"), CITIES_ONLY) is not None


@pytest.mark.parametrize(
    "location",
    [
        "Surabaya",
        "Surabaya, Indonesia",
        "Yogyakarta dan Sekitarnya",
        "Banten",
        "Cakung",
        "Indonesia",
        "Somewhere New, Indonesia",
        "  ",
    ],
)
@pytest.mark.parametrize("expected_locations", [["indonesia"], ["jakarta", "indonesia"]])
def test_indonesia_keeps_any_indonesian_region_literal_indonesia_and_blank(
    location: str, expected_locations: list[str]
):
    with _with_index():
        assert (
            filt.find_content_filter_failure(_job(location), {"location": expected_locations})
            is None
        )


@pytest.mark.parametrize("location", ["Bangkok", "Remote", "Bangkok, Thailand", "Singapore"])
@pytest.mark.parametrize("expected_locations", [["indonesia"], ["jakarta", "indonesia"]])
def test_indonesia_drops_foreign_and_unknown_places(location: str, expected_locations: list[str]):
    with _with_index():
        reason = filt.find_content_filter_failure(_job(location), {"location": expected_locations})

    assert reason is not None
    assert location in reason


def test_tangerang_selatan_kept():
    with _with_index():
        assert filt.find_content_filter_failure(_job("Tangerang Selatan"), JKT) is None


def test_kabupaten_bandung_kept():
    with _with_index():
        assert filt.find_content_filter_failure(_job("Kabupaten Bandung"), JKT) is None


def test_null_location_kept_with_index():  # existing semantics preserved
    with _with_index():
        assert filt.find_content_filter_failure(_job(None), JKT) is None


def test_other_keys_still_substring():
    with _with_index():
        job = _job("Jakarta")
        job["employment_type"] = "Full-time"
        assert filt.find_content_filter_failure(job, {"employment_type": ["full-time"]}) is None


def test_legacy_fallback_when_index_none():
    with patch.object(filt, "get_location_index", return_value=None):
        assert (
            filt.find_content_filter_failure(_job("Jakarta Selatan"), {"location": ["jakarta"]})
            is None
        )
        assert (
            filt.find_content_filter_failure(_job("Surabaya"), {"location": ["jakarta"]})
            is not None
        )


def test_location_filter_loads_index_through_cached_getter():
    index = build_wilayah_index(WILAYAH_ROWS)
    with patch.object(loc, "_load_wilayah_index_from_mongo", return_value=index) as loader:
        assert filt.find_content_filter_failure(_job("Cakung"), JKT) is None
        assert filt.find_content_filter_failure(_job("Bangkok"), JKT) is not None
    assert loader.call_count == 1


def test_location_filter_falls_back_to_substring_when_index_load_fails():
    with patch.object(loc, "_load_wilayah_index_from_mongo", return_value=None) as loader:
        assert (
            filt.find_content_filter_failure(_job("Jakarta Selatan"), {"location": ["jakarta"]})
            is None
        )
        assert (
            filt.find_content_filter_failure(_job("Surabaya"), {"location": ["jakarta"]})
            is not None
        )
    assert loader.call_count == 1


def test_filter_without_location_key_never_loads_index():
    job = _job("Jakarta")
    job["employment_type"] = "Full-time"
    with patch.object(loc, "_load_wilayah_index_from_mongo") as loader:
        assert filt.find_content_filter_failure(job, {"employment_type": ["full-time"]}) is None
        assert filt.find_content_filter_failure(job, {"location": []}) is None
    assert loader.call_count == 0


def test_blank_location_is_kept_when_only_cities_are_picked():
    with _with_index():
        assert filt.find_content_filter_failure(_job("   "), CITIES_ONLY) is None


def test_blank_location_is_kept_without_the_location_index():
    with patch.object(filt, "get_location_index", return_value=None):
        assert filt.find_content_filter_failure(_job(""), {"location": ["jakarta"]}) is None


def test_unresolved_location_is_dropped_with_an_unresolved_reason():
    with _with_index():
        reason = filt.find_content_filter_failure(_job("Jakarta Baru"), JKT)

    assert reason == f"location='Jakarta Baru' unresolved, not in {JKT['location']}"


def test_region_outside_the_picked_cities_is_dropped_with_an_out_of_scope_reason():
    with _with_index():
        reason = filt.find_content_filter_failure(_job("Surabaya"), CITIES_ONLY)

    assert reason == f"location='Surabaya' resolved out of scope, not in {CITIES_ONLY['location']}"


def test_legacy_substring_fallback_reports_the_untrimmed_location():
    with patch.object(filt, "get_location_index", return_value=None):
        kept_reason = filt.find_content_filter_failure(
            _job("  Jakarta Selatan  "), {"location": ["jakarta"]}
        )
        dropped_reason = filt.find_content_filter_failure(
            _job("Surabaya"), {"location": ["jakarta"]}
        )

    assert kept_reason is None
    assert dropped_reason == "location='Surabaya' not in ['jakarta']"


def test_legacy_substring_fallback_warns_only_once(
    monkeypatch: pytest.MonkeyPatch, scraper_log_records: pytest.LogCaptureFixture
):
    monkeypatch.setattr(filt, "_has_warned_about_missing_location_index", False)

    with patch.object(filt, "get_location_index", return_value=None):
        filt.find_content_filter_failure(_job("Surabaya"), {"location": ["jakarta"]})
        filt.find_content_filter_failure(_job("Bandung"), {"location": ["jakarta"]})

    legacy_warning_lines = list_log_lines_containing(
        list_warning_or_above_log_lines(scraper_log_records), "legacy substring"
    )
    assert len(legacy_warning_lines) == 1


def test_other_key_mismatch_reports_key_and_value():
    job = _job("Jakarta")
    job["employment_type"] = "Contract"

    reason = filt.find_content_filter_failure(job, {"employment_type": ["full-time"]})

    assert reason == "employment_type='Contract' not in ['full-time']"


def test_non_text_field_value_is_compared_as_text():
    job = _job("Jakarta")
    job["salary_min"] = 5000

    kept_reason = filt.find_content_filter_failure(job, {"salary_min": ["500"]})
    dropped_reason = filt.find_content_filter_failure(job, {"salary_min": ["9"]})

    assert kept_reason is None
    assert dropped_reason == "salary_min='5000' not in ['9']"


def test_first_failing_key_wins():
    job = _job("Surabaya")
    job["employment_type"] = "Contract"

    with patch.object(filt, "get_location_index", return_value=None):
        reason = filt.find_content_filter_failure(
            job, {"employment_type": ["full-time"], "location": ["jakarta"]}
        )

    assert reason == "employment_type='Contract' not in ['full-time']"


POSTED_AT_CUTOFF = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)


def _job_posted_at(posted_at: object) -> Job:
    job = empty_job("linkedin", "Backend Engineer", "Acme")
    job["posted_at"] = cast(Any, posted_at)
    return job


@pytest.mark.parametrize("posted_at", [None, 1767960000, POSTED_AT_CUTOFF])
def test_job_whose_posted_at_is_not_text_is_kept(posted_at: object):
    drop_reason = find_job_drop_reason(_job_posted_at(posted_at), {}, POSTED_AT_CUTOFF)

    assert drop_reason is None


@pytest.mark.parametrize("posted_at", ["yesterday", "", "2026-13-45T00:00:00"])
def test_job_whose_posted_at_text_is_not_a_date_is_kept(posted_at: str):
    drop_reason = find_job_drop_reason(_job_posted_at(posted_at), {}, POSTED_AT_CUTOFF)

    assert drop_reason is None


def test_posted_at_without_timezone_is_read_as_utc_and_kept_when_after_the_cutoff():
    one_hour_after_cutoff = "2026-01-10T13:00:00"

    drop_reason = find_job_drop_reason(_job_posted_at(one_hour_after_cutoff), {}, POSTED_AT_CUTOFF)

    assert drop_reason is None


def test_posted_at_exactly_at_the_cutoff_is_kept():
    drop_reason = find_job_drop_reason(
        _job_posted_at("2026-01-10T12:00:00+00:00"), {}, POSTED_AT_CUTOFF
    )

    assert drop_reason is None


def test_posted_at_without_timezone_is_read_as_utc_and_dropped_when_before_the_cutoff():
    one_hour_before_cutoff = "2026-01-10T11:00:00"

    drop_reason = find_job_drop_reason(_job_posted_at(one_hour_before_cutoff), {}, POSTED_AT_CUTOFF)

    assert drop_reason is not None
    assert drop_reason.kind == JobDropKind.STALE
    assert drop_reason.description == (
        "posted_at=2026-01-10T11:00:00 < cutoff=2026-01-10T12:00:00+00:00"
    )


def test_posted_at_with_another_timezone_is_compared_as_the_same_instant():
    one_hour_before_cutoff_in_jakarta_time = "2026-01-10T18:00:00+07:00"

    drop_reason = find_job_drop_reason(
        _job_posted_at(one_hour_before_cutoff_in_jakarta_time), {}, POSTED_AT_CUTOFF
    )

    assert drop_reason is not None
    assert drop_reason.kind == JobDropKind.STALE


def test_old_job_is_kept_when_there_is_no_cutoff():
    drop_reason = find_job_drop_reason(_job_posted_at("2000-01-01T00:00:00"), {}, None)

    assert drop_reason is None


def test_stale_reason_wins_over_filter_reason():
    job = _job_posted_at("2026-01-10T11:00:00")
    job["location"] = "Surabaya"

    with patch.object(filt, "get_location_index", return_value=None):
        drop_reason = find_job_drop_reason(job, {"location": ["jakarta"]}, POSTED_AT_CUTOFF)

    assert drop_reason is not None
    assert drop_reason.kind == JobDropKind.STALE


def test_recent_job_outside_the_filter_gets_a_filter_reason():
    job = _job_posted_at("2026-01-10T13:00:00")
    job["location"] = "Surabaya"

    with patch.object(filt, "get_location_index", return_value=None):
        drop_reason = find_job_drop_reason(job, {"location": ["jakarta"]}, POSTED_AT_CUTOFF)

    assert drop_reason is not None
    assert drop_reason.kind == JobDropKind.FILTER
    assert drop_reason.description == "location='Surabaya' not in ['jakarta']"
