from __future__ import annotations

import os
import re
import threading
import time
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from pymongo import MongoClient

from ..log import get_scraper_logger

_LOG = get_scraper_logger()

_UNICODE_COMPATIBILITY_FORM: Final = "NFKC"
_WHITESPACE_RUN = re.compile(r"\s+")
_LOCATION_SEGMENT_SEPARATOR = re.compile(r"\s*[,/·|]\s*|\s+-\s+")
_SEGMENT_EDGE_CHARACTERS = " -"

_MULTI_WORD_LEADING_QUALIFIERS = (
    "daerah khusus ibukota",
    "daerah istimewa",
    "kota administrasi",
    "kabupaten administrasi",
)
_SINGLE_WORD_LEADING_QUALIFIERS = (
    "kecamatan",
    "kabupaten",
    "kotamadya",
    "kelurahan",
    "provinsi",
    "administrasi",
    "kab",
    "kec",
    "kel",
    "prov",
    "kota",
    "desa",
    "area",
    "dki",
)
_LEADING_QUALIFIERS_MULTI_WORD_FIRST = (
    *_MULTI_WORD_LEADING_QUALIFIERS,
    *_SINGLE_WORD_LEADING_QUALIFIERS,
)
_TRAILING_QUALIFIERS = ("dan sekitarnya", "dan sekitar")

_REGION_CODE_LEVEL_SEPARATOR = "."
_LEVEL_SEPARATORS_IN_CITY_CODE = 1
_LEVEL_SEPARATORS_IN_DISTRICT_CODE = 2

_JAKARTA_PROVINCE_CODE = "31"
REGION_CODE_BY_ALIAS: dict[str, str] = {
    "jakarta raya": _JAKARTA_PROVINCE_CODE,
    "dki jakarta": _JAKARTA_PROVINCE_CODE,
    "dki": _JAKARTA_PROVINCE_CODE,
}

_WILAYAH_COLLECTION_NAME = "wilayah"
_REGION_CODE_FIELD = "_id"
_REGION_NAME_FIELD = "nama"
_PROVINCE_CITY_OR_DISTRICT_CODE_PATTERN = r"^\d{2}(\.\d{2}){0,2}$"
_PROVINCE_CITY_OR_DISTRICT_QUERY = {
    _REGION_CODE_FIELD: {"$regex": _PROVINCE_CITY_OR_DISTRICT_CODE_PATTERN}
}
_REGION_CODE_AND_NAME_PROJECTION = {_REGION_CODE_FIELD: 1, _REGION_NAME_FIELD: 1}
_DEFAULT_MONGO_URI = "mongodb://localhost:27017"
_DEFAULT_MONGO_DATABASE_NAME = "job_scraper"
_DEFAULT_SERVER_SELECTION_TIMEOUT_MS = "3000"

_FAILED_LOAD_RETRY_WAIT_SECONDS = 60
_LOCATION_INDEX_LOAD_LOCK = threading.Lock()
_cached_location_index: WilayahIndex | None = None
_last_failed_load_monotonic_seconds: float | None = None


@dataclass(frozen=True)
class WilayahIndex:
    region_codes_by_name: dict[str, list[str]]
    province_and_city_entries: tuple[tuple[str, str], ...]


def get_location_index() -> WilayahIndex | None:
    global _cached_location_index, _last_failed_load_monotonic_seconds
    if _cached_location_index is not None:
        return _cached_location_index
    if _is_waiting_to_retry_failed_load():
        return None
    with _LOCATION_INDEX_LOAD_LOCK:
        if _cached_location_index is not None:
            return _cached_location_index
        if _is_waiting_to_retry_failed_load():
            return None
        loaded_index = _load_wilayah_index_from_mongo()
        if loaded_index is None:
            _last_failed_load_monotonic_seconds = time.monotonic()
            return None
        _cached_location_index = loaded_index
        return loaded_index


def clear_cached_location_index() -> None:
    global _cached_location_index, _last_failed_load_monotonic_seconds
    with _LOCATION_INDEX_LOAD_LOCK:
        _cached_location_index = None
        _last_failed_load_monotonic_seconds = None


def normalize_location_text(location_text: str) -> str:
    compatibility_text = unicodedata.normalize(_UNICODE_COMPATIBILITY_FORM, location_text or "")
    lowercase_trimmed_text = compatibility_text.lower().strip()
    return _WHITESPACE_RUN.sub(" ", lowercase_trimmed_text)


def strip_region_qualifiers(normalized_location: str) -> str:
    remaining_text = normalized_location
    for trailing_qualifier in _TRAILING_QUALIFIERS:
        if remaining_text == trailing_qualifier:
            return normalized_location
        remaining_text = _strip_trailing_qualifier(remaining_text, trailing_qualifier)
    return _strip_all_leading_qualifiers(remaining_text)


def split_location_segments(normalized_location: str) -> list[str]:
    location_segments: list[str] = []
    for untrimmed_segment in _LOCATION_SEGMENT_SEPARATOR.split(normalized_location):
        location_segment = untrimmed_segment.strip(_SEGMENT_EDGE_CHARACTERS)
        if location_segment:
            location_segments.append(location_segment)
    return location_segments


def is_any_region_code_under_prefixes(
    region_codes: Iterable[str], region_code_prefixes: set[str] | frozenset[str]
) -> bool:
    for region_code in region_codes:
        for region_code_prefix in region_code_prefixes:
            if _is_region_code_under_prefix(region_code, region_code_prefix):
                return True
    return False


def build_wilayah_index(region_rows: Iterable[tuple[str, str]]) -> WilayahIndex:
    region_codes_by_name: dict[str, list[str]] = {}
    province_and_city_entries: list[tuple[str, str]] = []
    for region_code, region_name in region_rows:
        if _is_village_code(region_code):
            continue
        normalized_region_name = normalize_location_text(region_name)
        if not normalized_region_name:
            continue
        _add_region_code_for_name(region_codes_by_name, normalized_region_name, region_code)
        name_without_qualifiers = strip_region_qualifiers(normalized_region_name)
        if name_without_qualifiers:
            _add_region_code_for_name(region_codes_by_name, name_without_qualifiers, region_code)
        if _is_province_or_city_code(region_code):
            province_and_city_entries.append((region_code, normalized_region_name))
    return WilayahIndex(
        region_codes_by_name=region_codes_by_name,
        province_and_city_entries=tuple(province_and_city_entries),
    )


def find_candidate_region_codes(
    location: str,
    index: WilayahIndex,
    region_code_by_alias: dict[str, str] = REGION_CODE_BY_ALIAS,
) -> set[str]:
    normalized_location = normalize_location_text(location)
    if not normalized_location:
        return set()
    candidate_region_codes: set[str] = set()
    for location_name in _list_location_names_to_look_up(normalized_location):
        if location_name in region_code_by_alias:
            candidate_region_codes.add(region_code_by_alias[location_name])
        region_codes_with_name = index.region_codes_by_name.get(location_name, [])
        candidate_region_codes.update(region_codes_with_name)
    return candidate_region_codes


def find_region_code_prefixes_for_term(
    filter_term: str, province_and_city_entries: tuple[tuple[str, str], ...]
) -> set[str] | None:
    normalized_term = normalize_location_text(filter_term)
    matching_region_codes: list[str] = []
    for region_code, normalized_region_name in province_and_city_entries:
        if _contains_whole_word(normalized_region_name, normalized_term):
            matching_region_codes.append(region_code)
    if not matching_region_codes:
        return None
    return _keep_outermost_region_codes(matching_region_codes)


def _is_waiting_to_retry_failed_load() -> bool:
    failed_load_monotonic_seconds = _last_failed_load_monotonic_seconds
    if failed_load_monotonic_seconds is None:
        return False
    seconds_since_failed_load = time.monotonic() - failed_load_monotonic_seconds
    return seconds_since_failed_load < _FAILED_LOAD_RETRY_WAIT_SECONDS


def _load_wilayah_index_from_mongo() -> WilayahIndex | None:
    try:
        loaded_index = build_wilayah_index(_read_region_rows_from_mongo())
    except Exception as load_error:
        _LOG.warning(
            "[location] wilayah load failed (%s); location filter degraded, next try in %d s",
            load_error,
            _FAILED_LOAD_RETRY_WAIT_SECONDS,
        )
        return None
    if not loaded_index.region_codes_by_name:
        _LOG.warning(
            "[location] wilayah collection empty; location filter degraded, next try in %d s",
            _FAILED_LOAD_RETRY_WAIT_SECONDS,
        )
        return None
    _LOG.info(
        "[location] wilayah index loaded: %d names, %d entries",
        len(loaded_index.region_codes_by_name),
        len(loaded_index.province_and_city_entries),
    )
    return loaded_index


def _read_region_rows_from_mongo() -> list[tuple[str, str]]:
    mongo_uri = os.environ.get("MONGO_URI", _DEFAULT_MONGO_URI)
    database_name = os.environ.get("MONGO_DB_NAME", _DEFAULT_MONGO_DATABASE_NAME)
    server_selection_timeout_ms = int(
        os.environ.get("MONGO_SERVER_SELECTION_TIMEOUT_MS", _DEFAULT_SERVER_SELECTION_TIMEOUT_MS)
    )
    region_rows: list[tuple[str, str]] = []
    with MongoClient(
        mongo_uri, serverSelectionTimeoutMS=server_selection_timeout_ms
    ) as mongo_client:
        wilayah_collection = mongo_client[database_name][_WILAYAH_COLLECTION_NAME]
        region_documents = wilayah_collection.find(
            _PROVINCE_CITY_OR_DISTRICT_QUERY, _REGION_CODE_AND_NAME_PROJECTION
        )
        for region_document in region_documents:
            region_name = region_document.get(_REGION_NAME_FIELD) or ""
            region_rows.append((region_document[_REGION_CODE_FIELD], region_name))
    return region_rows


def _strip_trailing_qualifier(location_text: str, trailing_qualifier: str) -> str:
    if not location_text.endswith(" " + trailing_qualifier):
        return location_text
    text_before_qualifier = location_text[: -len(trailing_qualifier)]
    return text_before_qualifier.strip()


def _strip_all_leading_qualifiers(location_text: str) -> str:
    remaining_text = location_text
    shorter_text = _strip_one_leading_qualifier(remaining_text)
    while shorter_text != remaining_text:
        remaining_text = shorter_text
        shorter_text = _strip_one_leading_qualifier(remaining_text)
    return remaining_text


def _strip_one_leading_qualifier(location_text: str) -> str:
    for leading_qualifier in _LEADING_QUALIFIERS_MULTI_WORD_FIRST:
        qualifier_with_space = leading_qualifier + " "
        if not location_text.startswith(qualifier_with_space):
            continue
        text_after_qualifier = location_text[len(qualifier_with_space) :].strip()
        is_nothing_left_after_qualifier = not text_after_qualifier
        if is_nothing_left_after_qualifier:
            continue
        return text_after_qualifier
    return location_text


def _is_region_code_under_prefix(region_code: str, region_code_prefix: str) -> bool:
    if region_code == region_code_prefix:
        return True
    return region_code.startswith(region_code_prefix + _REGION_CODE_LEVEL_SEPARATOR)


def _is_village_code(region_code: str) -> bool:
    level_separator_count = region_code.count(_REGION_CODE_LEVEL_SEPARATOR)
    return level_separator_count > _LEVEL_SEPARATORS_IN_DISTRICT_CODE


def _is_province_or_city_code(region_code: str) -> bool:
    level_separator_count = region_code.count(_REGION_CODE_LEVEL_SEPARATOR)
    return level_separator_count <= _LEVEL_SEPARATORS_IN_CITY_CODE


def _add_region_code_for_name(
    region_codes_by_name: dict[str, list[str]], region_name: str, region_code: str
) -> None:
    region_codes_with_name = region_codes_by_name.setdefault(region_name, [])
    if region_code not in region_codes_with_name:
        region_codes_with_name.append(region_code)


def _list_location_names_to_look_up(normalized_location: str) -> list[str]:
    location_parts = split_location_segments(normalized_location)
    if normalized_location not in location_parts:
        location_parts = [*location_parts, normalized_location]
    location_names: list[str] = []
    for location_part in location_parts:
        location_names.append(location_part)
        part_without_qualifiers = strip_region_qualifiers(location_part)
        if part_without_qualifiers:
            location_names.append(part_without_qualifiers)
    return location_names


def _contains_whole_word(text: str, word: str) -> bool:
    whole_word_pattern = r"\b" + re.escape(word) + r"\b"
    return re.search(whole_word_pattern, text) is not None


def _keep_outermost_region_codes(region_codes: list[str]) -> set[str]:
    outermost_region_codes: set[str] = set()
    for region_code in region_codes:
        if not _is_inside_another_region(region_code, region_codes):
            outermost_region_codes.add(region_code)
    return outermost_region_codes


def _is_inside_another_region(region_code: str, other_region_codes: list[str]) -> bool:
    for other_region_code in other_region_codes:
        if other_region_code == region_code:
            continue
        if _is_region_code_under_prefix(region_code, other_region_code):
            return True
    return False
