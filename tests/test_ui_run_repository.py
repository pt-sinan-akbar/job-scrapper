from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

import mongomock
import pytest
from pymongo import MongoClient
from pymongo.errors import DocumentTooLarge, ServerSelectionTimeoutError

from ui_server.services import run_repository as run_repository_module
from ui_server.services.run_detail import RunDetail
from ui_server.services.run_record import DiscordStatus, RunRecord, RunStatus
from ui_server.services.run_repository import (
    BREAKER_SECONDS,
    RUN_STORE_TIMEOUT_MS,
    UI_RUNS_COLLECTION,
    MongoRunRepository,
    RunStoreUnavailableError,
    open_run_repository,
)

UNREACHABLE_URI = "mongodb://127.0.0.1:1"
FAST_TIMEOUT_MS = 50


def _detail(run_id: str) -> RunDetail:
    record = RunRecord(
        id=run_id,
        status=RunStatus.SUCCEEDED,
        keywords=("django",),
        sites=("upwork",),
        started_at="2026-11-18T01:00:00+00:00",
        finished_at="2026-11-18T01:01:00+00:00",
        job_count=1,
    )
    job = {
        "site": "upwork",
        "matched_keyword": "django",
        "title": "A",
        "company": None,
        "location": None,
        "url": None,
        "posted_at": None,
        "salary_min": 1000,
        "salary_max": 2000.5,
        "work_type": "remote",
        "experience_level": None,
    }
    payload = {"keyword": "django", "site": "upwork", "raw": {"a": 1}, "filtered": None}
    return RunDetail(record, (job,), (), (payload,))


@pytest.fixture
def database() -> Any:
    return mongomock.MongoClient()["job_scraper"]


@pytest.fixture
def repository(database: Any) -> MongoRunRepository:
    return MongoRunRepository(database)


def test_uses_the_ui_runs_collection():
    assert UI_RUNS_COLLECTION == "ui_runs"


def test_save_then_find_and_latest_return_the_detail(repository: MongoRunRepository):
    detail = _detail("20261118T010000Z-aaaaaa")

    repository.save(detail)

    assert repository.find(detail.record.id) == detail
    assert repository.latest() == detail


def test_save_keeps_only_the_latest_run(repository: MongoRunRepository, database: Any):
    repository.save(_detail("20261118T010000Z-aaaaaa"))
    repository.save(_detail("20261118T020000Z-bbbbbb"))

    documents = list(database[UI_RUNS_COLLECTION].find())

    assert [document["_id"] for document in documents] == ["20261118T020000Z-bbbbbb"]
    assert repository.find("20261118T010000Z-aaaaaa") is None


def test_saving_the_same_run_twice_keeps_one_document(
    repository: MongoRunRepository, database: Any
):
    detail = _detail("20261118T010000Z-aaaaaa")

    repository.save(detail)
    repository.save(detail)

    assert database[UI_RUNS_COLLECTION].count_documents({}) == 1


def test_save_record_updates_only_the_record(repository: MongoRunRepository):
    detail = _detail("20261118T010000Z-aaaaaa")
    repository.save(detail)
    updated = replace(detail.record, discord_status=DiscordStatus.SENT, discord_sent=1)

    repository.save_record(updated)

    assert repository.find(detail.record.id) == replace(detail, record=updated)


def test_find_and_latest_without_runs_return_none(repository: MongoRunRepository):
    assert repository.find("20261118T010000Z-aaaaaa") is None
    assert repository.latest() is None


def test_unreadable_document_is_treated_as_missing(
    repository: MongoRunRepository, database: Any, caplog: pytest.LogCaptureFixture
):
    database[UI_RUNS_COLLECTION].insert_one({"_id": "broken", "record": {"id": "broken"}})

    with caplog.at_level(logging.WARNING, logger="scraper-ui"):
        assert repository.latest() is None
        assert repository.find("broken") is None

    assert "unreadable" in caplog.text


def test_unreachable_mongo_never_raises_on_writes_or_latest(caplog: pytest.LogCaptureFixture):
    client: Any = MongoClient(UNREACHABLE_URI, serverSelectionTimeoutMS=FAST_TIMEOUT_MS)
    repository = MongoRunRepository(client["job_scraper"])
    detail = _detail("20261118T010000Z-aaaaaa")

    with caplog.at_level(logging.WARNING, logger="scraper-ui"):
        repository.save(detail)
        repository.save_record(detail.record)
        assert repository.latest() is None

    assert "ui_runs" in caplog.text


def test_find_on_unreachable_mongo_raises_store_unavailable():
    client: Any = MongoClient(UNREACHABLE_URI, serverSelectionTimeoutMS=FAST_TIMEOUT_MS)
    repository = MongoRunRepository(client["job_scraper"])

    with pytest.raises(RunStoreUnavailableError):
        repository.find("20261118T010000Z-aaaaaa")


class _Flaky:
    def __init__(self, collection: Any, failures: dict[str, Exception]) -> None:
        self._collection = collection
        self.failures = failures
        self.calls: list[str] = []

    def __getattr__(self, name: str) -> Any:
        operation = getattr(self._collection, name)

        def call(*args: Any, **kwargs: Any) -> Any:
            self.calls.append(name)
            failure = self.failures.get(name)
            if failure is not None:
                raise failure
            return operation(*args, **kwargs)

        return call


class _TooLargeWithPayloads(_Flaky):
    def replace_one(self, query: Any, document: dict[str, Any], **kwargs: Any) -> Any:
        self.calls.append("replace_one")
        if document.get("payloads"):
            raise DocumentTooLarge("too large")
        return self._collection.replace_one(query, document, **kwargs)


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _flaky_repository(flaky: _Flaky, clock: _Clock | None = None) -> MongoRunRepository:
    return MongoRunRepository({UI_RUNS_COLLECTION: flaky}, clock=clock or _Clock())


def test_save_too_large_retries_without_payloads(database: Any, caplog: pytest.LogCaptureFixture):
    collection = database[UI_RUNS_COLLECTION]
    MongoRunRepository(database).save(_detail("20261118T010000Z-aaaaaa"))
    repository = _flaky_repository(_TooLargeWithPayloads(collection, {}))
    detail = _detail("20261118T020000Z-bbbbbb")

    with caplog.at_level(logging.WARNING, logger="scraper-ui"):
        repository.save(detail)

    stored = MongoRunRepository(database)
    assert stored.latest() == RunDetail(detail.record, detail.jobs, detail.failures, ())
    assert stored.find("20261118T010000Z-aaaaaa") is None
    assert "without payloads" in caplog.text
    assert "bytes" in caplog.text


def test_save_failing_twice_clears_stored_runs_so_latest_is_empty(database: Any):
    collection = database[UI_RUNS_COLLECTION]
    MongoRunRepository(database).save(_detail("20261118T010000Z-aaaaaa"))
    flaky = _Flaky(collection, {"replace_one": DocumentTooLarge("too large")})

    _flaky_repository(flaky).save(_detail("20261118T020000Z-bbbbbb"))

    assert flaky.calls.count("replace_one") == 2
    assert collection.count_documents({}) == 0
    assert MongoRunRepository(database).latest() is None


def test_save_record_upserts_when_the_document_is_missing(repository: MongoRunRepository):
    record = _detail("20261118T010000Z-aaaaaa").record

    repository.save_record(record)

    assert repository.find(record.id) == RunDetail(record)
    assert repository.latest() == RunDetail(record)


def test_save_record_keeps_jobs_of_an_existing_document(repository: MongoRunRepository):
    detail = _detail("20261118T010000Z-aaaaaa")
    repository.save(detail)
    updated = replace(detail.record, discord_status=DiscordStatus.FAILED)

    repository.save_record(updated)

    assert repository.find(detail.record.id) == replace(detail, record=updated)


def test_connection_failure_skips_mongo_for_a_while_and_logs_once(
    database: Any, caplog: pytest.LogCaptureFixture
):
    flaky = _Flaky(database[UI_RUNS_COLLECTION], {"find_one": ServerSelectionTimeoutError("x")})
    clock = _Clock()
    repository = _flaky_repository(flaky, clock)
    detail = _detail("20261118T010000Z-aaaaaa")

    with caplog.at_level(logging.WARNING, logger="scraper-ui"):
        assert repository.latest() is None
        with pytest.raises(RunStoreUnavailableError):
            repository.find(detail.record.id)
        repository.save(detail)
        repository.save_record(detail.record)

    assert flaky.calls == ["find_one"]
    assert caplog.text.count("ui_runs") == 1


def test_mongo_is_tried_again_after_the_breaker_time(database: Any):
    flaky = _Flaky(database[UI_RUNS_COLLECTION], {"find_one": ServerSelectionTimeoutError("x")})
    clock = _Clock()
    repository = _flaky_repository(flaky, clock)
    repository.latest()

    clock.now += BREAKER_SECONDS + 1
    flaky.failures = {}

    assert repository.latest() is None
    assert flaky.calls == ["find_one", "find_one"]


def test_breaker_lasts_about_thirty_seconds():
    assert BREAKER_SECONDS == 30


def test_document_errors_do_not_open_the_breaker(database: Any):
    flaky = _TooLargeWithPayloads(database[UI_RUNS_COLLECTION], {})
    repository = _flaky_repository(flaky)

    repository.save(_detail("20261118T010000Z-aaaaaa"))
    repository.save(_detail("20261118T020000Z-bbbbbb"))

    assert flaky.calls.count("replace_one") == 4


def test_run_store_client_uses_a_short_server_selection_timeout(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("MONGO_URI", UNREACHABLE_URI)
    monkeypatch.setenv("MONGO_DB_NAME", "ui_test_db")
    captured: dict[str, Any] = {}

    def fake_client(uri: str, **options: Any) -> dict[str, Any]:
        captured.update(uri=uri, **options)
        return {"ui_test_db": mongomock.MongoClient()["ui_test_db"]}

    monkeypatch.setattr(run_repository_module, "MongoClient", fake_client)

    repository = open_run_repository()

    assert isinstance(repository, MongoRunRepository)
    assert captured["uri"] == UNREACHABLE_URI
    assert captured["serverSelectionTimeoutMS"] == RUN_STORE_TIMEOUT_MS == 1000
