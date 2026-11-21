from __future__ import annotations

import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any

import pytest

import scraper.sites._location as loc
from scraper.sites._location import (
    WilayahIndex,
    build_wilayah_index,
    find_candidate_region_codes,
    find_region_code_prefixes_for_term,
    is_any_region_code_under_prefixes,
    normalize_location_text,
    split_location_segments,
    strip_region_qualifiers,
)
from tests.wilayah_rows import WILAYAH_ROWS

_REAL_LOAD_WILAYAH_INDEX_FROM_MONGO = loc._load_wilayah_index_from_mongo


def test_normalize_collapses_ws_and_lowercases():
    normalized = normalize_location_text("  Kota Administrasi   Jakarta Utara ")
    assert normalized == "kota administrasi jakarta utara"


def test_strip_leading_qualifiers_iteratively():
    assert strip_region_qualifiers("area dki jakarta") == "jakarta"
    assert strip_region_qualifiers("kecamatan tanjung priok") == "tanjung priok"
    assert strip_region_qualifiers("daerah khusus ibukota jakarta") == "jakarta"
    assert strip_region_qualifiers("kota administrasi jakarta utara") == "jakarta utara"


def test_strip_trailing_qualifier():
    assert strip_region_qualifiers("yogyakarta dan sekitarnya") == "yogyakarta"
    assert strip_region_qualifiers("kota bandung dan sekitar") == "bandung"


def test_strip_keeps_bare_leading_qualifier_instead_of_returning_empty():
    assert strip_region_qualifiers("kota") == "kota"


def test_strip_keeps_text_that_is_only_a_trailing_qualifier():
    assert strip_region_qualifiers("dan sekitarnya") == "dan sekitarnya"
    assert strip_region_qualifiers("dan sekitar dan sekitarnya") == "dan sekitar dan sekitarnya"


def test_segments_splits_on_comma_and_slash():
    assert split_location_segments("jakarta raya, indonesia") == ["jakarta raya", "indonesia"]
    assert split_location_segments("bandung / jawa barat") == ["bandung", "jawa barat"]


def test_segments_split_on_spaced_dash_and_drop_empty_parts():
    assert split_location_segments("jakarta - indonesia") == ["jakarta", "indonesia"]
    assert split_location_segments("jakarta,, -") == ["jakarta"]


def test_region_code_is_under_its_own_prefix_and_parent_prefix():
    assert is_any_region_code_under_prefixes({"31.75.06"}, {"31"}) is True
    assert is_any_region_code_under_prefixes({"31"}, {"31"}) is True


def test_region_code_is_not_under_another_region():
    assert is_any_region_code_under_prefixes({"32.73"}, {"31"}) is False


def test_region_code_sharing_only_leading_digits_is_not_under_prefix():
    assert is_any_region_code_under_prefixes({"310"}, {"31"}) is False


def test_one_region_code_under_one_of_several_prefixes_is_enough():
    assert is_any_region_code_under_prefixes({"35.78", "31.75.06"}, {"32", "31.75"}) is True
    assert is_any_region_code_under_prefixes({"35.78", "34"}, {"32", "31.75"}) is False


def test_no_region_code_or_no_prefix_is_never_under():
    assert is_any_region_code_under_prefixes(set(), {"31"}) is False
    assert is_any_region_code_under_prefixes({"31"}, set()) is False


def _idx() -> WilayahIndex:
    return build_wilayah_index(WILAYAH_ROWS)


def test_villages_excluded_cakung_resolves_to_jakarta_only():
    assert find_candidate_region_codes("Cakung", _idx()) == {"31.75.06"}


def test_index_keeps_only_provinces_and_cities_as_filter_term_entries():
    entry_codes = {region_code for region_code, _ in _idx().province_and_city_entries}
    assert "31" in entry_codes
    assert "31.71" in entry_codes
    assert "31.72.02" not in entry_codes


def test_index_finds_region_by_full_name_and_by_name_without_qualifiers():
    names = _idx().region_codes_by_name
    assert names["kota bekasi"] == ["32.75"]
    assert names["bekasi"] == ["32.75", "32.16"]


def test_resolve_area_dki_jakarta():
    assert find_candidate_region_codes("Area DKI Jakarta", _idx()) == {"31"}


def test_resolve_bare_jakarta_to_province():
    assert find_candidate_region_codes("Jakarta", _idx()) == {"31"}


def test_resolve_kecamatan_prefix():
    assert find_candidate_region_codes("Kecamatan Tanjung Priok", _idx()) == {"31.72.02"}


def test_resolve_alias_jakarta_raya():
    assert find_candidate_region_codes("Jakarta Raya", _idx()) == {"31"}


def test_resolve_uses_given_aliases():
    aliases = {"kota kembang": "32.73"}
    assert find_candidate_region_codes("Kota Kembang", _idx(), aliases) == {"32.73"}


def test_resolve_each_segment_of_compound_location():
    assert find_candidate_region_codes("Surabaya, Bekasi", _idx()) == {"35.78", "32.75", "32.16"}


def test_resolve_blank_and_unknown_locations_to_nothing():
    assert find_candidate_region_codes("   ", _idx()) == set()
    assert find_candidate_region_codes("Atlantis", _idx()) == set()


def test_term_prefixes_jakarta_is_province():
    entries = _idx().province_and_city_entries
    assert find_region_code_prefixes_for_term("jakarta", entries) == {"31"}


def test_term_prefixes_tangerang_three_cities():
    entries = _idx().province_and_city_entries
    assert find_region_code_prefixes_for_term("tangerang", entries) == {"36.71", "36.03", "36.74"}


def test_term_prefixes_bandung_three():
    entries = _idx().province_and_city_entries
    assert find_region_code_prefixes_for_term("bandung", entries) == {"32.73", "32.04", "32.17"}


def test_term_prefixes_indonesia_is_literal():
    entries = _idx().province_and_city_entries
    assert find_region_code_prefixes_for_term("indonesia", entries) is None


class _CountingLoader:
    def __init__(self, results: list[WilayahIndex | None]) -> None:
        self._results = list(results)
        self.call_count = 0

    def __call__(self) -> WilayahIndex | None:
        self.call_count += 1
        return self._results.pop(0)


def _use_loader(monkeypatch: pytest.MonkeyPatch, loader: Any) -> None:
    monkeypatch.setattr(loc, "_load_wilayah_index_from_mongo", loader)


def _use_clock(monkeypatch: pytest.MonkeyPatch, clock: dict[str, float]) -> None:
    monkeypatch.setattr(loc, "time", SimpleNamespace(monotonic=lambda: clock["now"]))


def test_successful_load_is_cached_for_later_calls(monkeypatch: pytest.MonkeyPatch):
    index = _idx()
    loader = _CountingLoader([index])
    _use_loader(monkeypatch, loader)

    assert loc.get_location_index() is index
    assert loc.get_location_index() is index
    assert loader.call_count == 1


def test_failed_load_returns_none_and_is_not_retried_inside_wait(monkeypatch: pytest.MonkeyPatch):
    clock = {"now": 1000.0}
    loader = _CountingLoader([None, _idx()])
    _use_loader(monkeypatch, loader)
    _use_clock(monkeypatch, clock)

    assert loc.get_location_index() is None
    clock["now"] += loc._FAILED_LOAD_RETRY_WAIT_SECONDS - 1
    assert loc.get_location_index() is None
    assert loader.call_count == 1


def test_failed_load_is_retried_after_wait_and_then_cached(monkeypatch: pytest.MonkeyPatch):
    clock = {"now": 1000.0}
    index = _idx()
    loader = _CountingLoader([None, index])
    _use_loader(monkeypatch, loader)
    _use_clock(monkeypatch, clock)

    assert loc.get_location_index() is None
    clock["now"] += loc._FAILED_LOAD_RETRY_WAIT_SECONDS
    assert loc.get_location_index() is index
    assert loc.get_location_index() is index
    assert loader.call_count == 2


def test_each_failed_load_starts_a_new_wait(monkeypatch: pytest.MonkeyPatch):
    clock = {"now": 1000.0}
    loader = _CountingLoader([None, None, _idx()])
    _use_loader(monkeypatch, loader)
    _use_clock(monkeypatch, clock)

    assert loc.get_location_index() is None
    clock["now"] += loc._FAILED_LOAD_RETRY_WAIT_SECONDS
    assert loc.get_location_index() is None
    clock["now"] += loc._FAILED_LOAD_RETRY_WAIT_SECONDS - 1
    assert loc.get_location_index() is None
    assert loader.call_count == 2


def test_clear_forgets_cached_index(monkeypatch: pytest.MonkeyPatch):
    first, second = _idx(), _idx()
    loader = _CountingLoader([first, second])
    _use_loader(monkeypatch, loader)

    assert loc.get_location_index() is first
    loc.clear_cached_location_index()
    assert loc.get_location_index() is second


def test_clear_forgets_failed_load_so_next_call_loads_at_once(monkeypatch: pytest.MonkeyPatch):
    index = _idx()
    loader = _CountingLoader([None, index])
    _use_loader(monkeypatch, loader)
    _use_clock(monkeypatch, {"now": 1000.0})

    assert loc.get_location_index() is None
    loc.clear_cached_location_index()
    assert loc.get_location_index() is index


class _LockThatReportsEachEntryAttempt:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.entry_attempts = threading.Semaphore(0)

    def __enter__(self) -> None:
        self.entry_attempts.release()
        self._lock.acquire()

    def __exit__(self, *exc_info: object) -> None:
        self._lock.release()


def _get_index_from_threads_that_all_wait_for_one_load(
    monkeypatch: pytest.MonkeyPatch, load_result: WilayahIndex | None
) -> tuple[list[str], list[WilayahIndex | None]]:
    thread_count = 8
    reporting_lock = _LockThatReportsEachEntryAttempt()
    allow_load_to_finish = threading.Event()
    load_calls: list[str] = []

    def loader_held_until_all_threads_wait() -> WilayahIndex | None:
        load_calls.append(threading.current_thread().name)
        allow_load_to_finish.wait(timeout=5)
        return load_result

    monkeypatch.setattr(loc, "_LOCATION_INDEX_LOAD_LOCK", reporting_lock)
    _use_loader(monkeypatch, loader_held_until_all_threads_wait)

    with ThreadPoolExecutor(max_workers=thread_count) as executor:
        futures = [executor.submit(loc.get_location_index) for _ in range(thread_count)]
        reached_lock = [
            reporting_lock.entry_attempts.acquire(timeout=5) for _ in range(thread_count)
        ]
        allow_load_to_finish.set()
        results = [future.result(timeout=5) for future in futures]

    assert all(reached_lock)
    assert len(results) == thread_count
    return load_calls, results


def test_concurrent_first_calls_load_only_once(monkeypatch: pytest.MonkeyPatch):
    index = _idx()

    load_calls, results = _get_index_from_threads_that_all_wait_for_one_load(monkeypatch, index)

    assert len(load_calls) == 1
    assert all(result is index for result in results)


def test_concurrent_first_calls_try_a_failing_load_only_once(monkeypatch: pytest.MonkeyPatch):
    load_calls, results = _get_index_from_threads_that_all_wait_for_one_load(monkeypatch, None)

    assert len(load_calls) == 1
    assert all(result is None for result in results)


def test_clear_resets_the_cache_while_holding_the_load_lock(monkeypatch: pytest.MonkeyPatch):
    reporting_lock = _LockThatReportsEachEntryAttempt()
    monkeypatch.setattr(loc, "_LOCATION_INDEX_LOAD_LOCK", reporting_lock)

    loc.clear_cached_location_index()

    assert reporting_lock.entry_attempts.acquire(blocking=False) is True
    assert reporting_lock.entry_attempts.acquire(blocking=False) is False


class _FakeMongoClient:
    def __init__(self, documents: list[dict[str, Any]], find_error: Exception | None = None):
        self._documents = documents
        self._find_error = find_error
        self.is_closed = False
        self.opened_names: list[str] = []

    def __enter__(self) -> _FakeMongoClient:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.is_closed = True

    def __getitem__(self, name: str) -> _FakeMongoClient:
        self.opened_names.append(name)
        return self

    def find(self, query: dict[str, Any], projection: dict[str, int]) -> Iterator[dict[str, Any]]:
        if self._find_error is not None:
            raise self._find_error
        return self._yield_documents_while_open()

    def _yield_documents_while_open(self) -> Iterator[dict[str, Any]]:
        for document in self._documents:
            if self.is_closed:
                raise RuntimeError("cursor was read after the client was closed")
            yield document


def _use_mongo_client(monkeypatch: pytest.MonkeyPatch, client: _FakeMongoClient) -> None:
    monkeypatch.setattr(loc, "MongoClient", lambda *args, **kwargs: client)


def test_mongo_loader_builds_index_and_closes_client(monkeypatch: pytest.MonkeyPatch):
    documents = [{"_id": "31", "nama": "DKI Jakarta"}, {"_id": "32.73", "nama": "Kota Bandung"}]
    client = _FakeMongoClient(documents)
    _use_mongo_client(monkeypatch, client)
    monkeypatch.setenv("MONGO_DB_NAME", "some_db")

    index = _REAL_LOAD_WILAYAH_INDEX_FROM_MONGO()

    assert index is not None
    assert index.region_codes_by_name["bandung"] == ["32.73"]
    assert client.opened_names == ["some_db", "wilayah"]
    assert client.is_closed is True


def test_mongo_loader_skips_document_without_name(monkeypatch: pytest.MonkeyPatch):
    documents = [{"_id": "31"}, {"_id": "32.73", "nama": "Kota Bandung"}]
    _use_mongo_client(monkeypatch, _FakeMongoClient(documents))

    index = _REAL_LOAD_WILAYAH_INDEX_FROM_MONGO()

    assert index is not None
    assert index.province_and_city_entries == (("32.73", "kota bandung"),)


def test_mongo_loader_returns_none_and_closes_client_when_query_fails(
    monkeypatch: pytest.MonkeyPatch,
):
    client = _FakeMongoClient([], find_error=RuntimeError("server unreachable"))
    _use_mongo_client(monkeypatch, client)

    assert _REAL_LOAD_WILAYAH_INDEX_FROM_MONGO() is None
    assert client.is_closed is True


def test_mongo_loader_returns_none_when_collection_is_empty(monkeypatch: pytest.MonkeyPatch):
    client = _FakeMongoClient([])
    _use_mongo_client(monkeypatch, client)

    assert _REAL_LOAD_WILAYAH_INDEX_FROM_MONGO() is None
    assert client.is_closed is True


def test_mongo_loader_returns_none_when_client_cannot_be_created(monkeypatch: pytest.MonkeyPatch):
    def refuse_to_connect(*args: Any, **kwargs: Any) -> _FakeMongoClient:
        raise RuntimeError("bad uri")

    monkeypatch.setattr(loc, "MongoClient", refuse_to_connect)

    assert _REAL_LOAD_WILAYAH_INDEX_FROM_MONGO() is None


def test_mongo_loader_returns_none_when_timeout_setting_is_not_a_number(
    monkeypatch: pytest.MonkeyPatch,
):
    _use_mongo_client(monkeypatch, _FakeMongoClient([{"_id": "31", "nama": "DKI Jakarta"}]))
    monkeypatch.setenv("MONGO_SERVER_SELECTION_TIMEOUT_MS", "soon")

    assert _REAL_LOAD_WILAYAH_INDEX_FROM_MONGO() is None
