from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, Protocol, TypeVar

import bson
from bson.errors import BSONError
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, PyMongoError

from ui_server.services.run_detail import (
    RunDetail,
    detail_from_dict,
    detail_to_dict,
    record_to_dict,
)
from ui_server.services.run_record import RunRecord

LOG = logging.getLogger("scraper-ui")
UI_RUNS_COLLECTION = "ui_runs"
STORE_ERRORS = (PyMongoError, BSONError)
UNAVAILABLE_ERRORS = (ConnectionFailure,)
UNREADABLE_ERRORS = (KeyError, TypeError, ValueError)
BREAKER_SECONDS = 30
RUN_STORE_TIMEOUT_MS = 1000
DEFAULT_MONGO_URI = "mongodb://localhost:27017"
DEFAULT_DB_NAME = "job_scraper"

T = TypeVar("T")


class RunStoreError(Exception):
    pass


class RunStoreUnavailableError(RunStoreError):
    pass


class RunRepository(Protocol):
    def save(self, detail: RunDetail) -> None: ...

    def save_record(self, record: RunRecord) -> None: ...

    def find(self, run_id: str) -> RunDetail | None: ...

    def latest(self) -> RunDetail | None: ...


def _to_detail(document: dict[str, Any] | None) -> RunDetail | None:
    if document is None:
        return None
    try:
        return detail_from_dict(document)
    except UNREADABLE_ERRORS as exc:
        LOG.warning("unreadable ui_runs document %s: %r", document.get("_id"), exc)
        return None


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _document(detail: RunDetail) -> dict[str, Any]:
    return {**detail_to_dict(detail), "_id": detail.record.id, "saved_at": _now()}


def _size(document: dict[str, Any]) -> str:
    try:
        return str(len(bson.encode(document)))
    except (BSONError, TypeError, ValueError):
        return "unknown"


def _record_upsert(record: RunRecord) -> dict[str, Any]:
    return {
        "$set": {"record": record_to_dict(record)},
        "$setOnInsert": {"jobs": [], "failures": [], "payloads": [], "saved_at": _now()},
    }


class MongoRunRepository:
    def __init__(
        self,
        database: Any,
        clock: Callable[[], float] = time.monotonic,
        breaker_seconds: float = BREAKER_SECONDS,
    ) -> None:
        self._collection = database[UI_RUNS_COLLECTION]
        self._clock = clock
        self._breaker_seconds = breaker_seconds
        self._paused_until = float("-inf")

    def save(self, detail: RunDetail) -> None:
        document = _document(detail)
        try:
            self._call("save", lambda: self._replace_all(document))
        except RunStoreUnavailableError:
            return
        except RunStoreError:
            self._save_without_payloads(detail, document)

    def save_record(self, record: RunRecord) -> None:
        update = _record_upsert(record)
        with suppress(RunStoreError):
            self._call(
                "update",
                lambda: self._collection.update_one({"_id": record.id}, update, upsert=True),
            )

    def find(self, run_id: str) -> RunDetail | None:
        try:
            document = self._call("read", lambda: self._collection.find_one({"_id": run_id}))
        except RunStoreError as exc:
            raise RunStoreUnavailableError(str(exc)) from exc
        return _to_detail(document)

    def latest(self) -> RunDetail | None:
        try:
            document = self._call(
                "read", lambda: self._collection.find_one({}, sort=[("saved_at", -1)])
            )
        except RunStoreError:
            return None
        return _to_detail(document)

    def _save_without_payloads(self, detail: RunDetail, document: dict[str, Any]) -> None:
        LOG.warning(
            "ui_runs save of run %s failed at %s bytes, retrying without payloads",
            detail.record.id,
            _size(document),
        )
        slim = _document(replace(detail, payloads=()))
        try:
            self._call("save without payloads", lambda: self._replace_all(slim))
        except RunStoreUnavailableError:
            return
        except RunStoreError:
            self._clear(detail.record.id)

    def _clear(self, run_id: str) -> None:
        LOG.warning("ui_runs could not store run %s, removing stored runs", run_id)
        with suppress(RunStoreError):
            self._call("clear", lambda: self._collection.delete_many({}))

    def _replace_all(self, document: dict[str, Any]) -> None:
        run_id = document["_id"]
        self._collection.replace_one({"_id": run_id}, document, upsert=True)
        self._collection.delete_many({"_id": {"$ne": run_id}})

    def _call(self, action: str, operation: Callable[[], T]) -> T:
        if self._clock() < self._paused_until:
            raise RunStoreUnavailableError("run storage is paused after a failure")
        try:
            return operation()
        except UNAVAILABLE_ERRORS as exc:
            self._pause(action, exc)
            raise RunStoreUnavailableError(str(exc)) from exc
        except STORE_ERRORS as exc:
            LOG.warning("ui_runs %s failed: %s", action, exc)
            raise RunStoreError(str(exc)) from exc

    def _pause(self, action: str, exc: Exception) -> None:
        self._paused_until = self._clock() + self._breaker_seconds
        LOG.warning(
            "ui_runs %s failed, skipping run storage for %d s, run results stay in memory: %s",
            action,
            self._breaker_seconds,
            exc,
        )


def open_run_repository() -> MongoRunRepository:
    uri = os.environ.get("MONGO_URI", DEFAULT_MONGO_URI)
    name = os.environ.get("MONGO_DB_NAME", DEFAULT_DB_NAME)
    client: Any = MongoClient(
        uri,
        serverSelectionTimeoutMS=RUN_STORE_TIMEOUT_MS,
        connectTimeoutMS=RUN_STORE_TIMEOUT_MS,
    )
    return MongoRunRepository(client[name])
