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

from backend.services.scrape_report import (
    ScrapeReport,
    convert_report_to_document,
    convert_summary_to_dict,
    read_report_from_document,
)
from backend.services.scrape_summary import ScrapeSummary

LOG = logging.getLogger("scraper-ui")
SCRAPE_REPORTS_COLLECTION = "ui_runs"
STORE_ERRORS = (PyMongoError, BSONError)
UNAVAILABLE_ERRORS = (ConnectionFailure,)
UNREADABLE_ERRORS = (KeyError, TypeError, ValueError)
BREAKER_SECONDS = 30
SCRAPE_STORE_TIMEOUT_MS = 1000
DEFAULT_MONGO_URI = "mongodb://localhost:27017"
DEFAULT_DB_NAME = "job_scraper"

OperationValue = TypeVar("OperationValue")


class ScrapeStoreError(Exception):
    pass


class ScrapeStoreUnavailableError(ScrapeStoreError):
    pass


class ScrapeReportRepository(Protocol):
    def save(self, scrape_report: ScrapeReport) -> None: ...

    def save_summary(self, scrape_summary: ScrapeSummary) -> None: ...

    def find(self, scrape_id: str) -> ScrapeReport | None: ...

    def find_latest(self) -> ScrapeReport | None: ...


class MongoScrapeReportRepository:
    def __init__(
        self,
        database: Any,
        clock: Callable[[], float] = time.monotonic,
        breaker_seconds: float = BREAKER_SECONDS,
    ) -> None:
        self._collection = database[SCRAPE_REPORTS_COLLECTION]
        self._clock = clock
        self._breaker_seconds = breaker_seconds
        self._paused_until = float("-inf")

    def save(self, scrape_report: ScrapeReport) -> None:
        report_document = _build_report_document(scrape_report)
        try:
            self._call_store("save", lambda: self._replace_all_reports(report_document))
        except ScrapeStoreUnavailableError:
            return
        except ScrapeStoreError:
            self._save_without_payloads(scrape_report, report_document)

    def save_summary(self, scrape_summary: ScrapeSummary) -> None:
        summary_upsert = _build_summary_upsert(scrape_summary)
        with suppress(ScrapeStoreError):
            self._call_store(
                "update",
                lambda: self._collection.update_one(
                    {"_id": scrape_summary.id}, summary_upsert, upsert=True
                ),
            )

    def find(self, scrape_id: str) -> ScrapeReport | None:
        try:
            document = self._call_store(
                "read", lambda: self._collection.find_one({"_id": scrape_id})
            )
        except ScrapeStoreError as exc:
            raise ScrapeStoreUnavailableError(str(exc)) from exc
        return _read_report_or_none(document)

    def find_latest(self) -> ScrapeReport | None:
        try:
            document = self._call_store(
                "read", lambda: self._collection.find_one({}, sort=[("saved_at", -1)])
            )
        except ScrapeStoreError:
            return None
        return _read_report_or_none(document)

    def _save_without_payloads(
        self, scrape_report: ScrapeReport, report_document: dict[str, Any]
    ) -> None:
        LOG.warning(
            "ui_runs save of scrape %s failed at %s bytes, retrying without payloads",
            scrape_report.summary.id,
            _measure_document_size(report_document),
        )
        slim_document = _build_report_document(replace(scrape_report, payloads=()))
        try:
            self._call_store(
                "save without payloads", lambda: self._replace_all_reports(slim_document)
            )
        except ScrapeStoreUnavailableError:
            return
        except ScrapeStoreError:
            self._clear_stored_reports(scrape_report.summary.id)

    def _clear_stored_reports(self, scrape_id: str) -> None:
        LOG.warning("ui_runs could not store scrape %s, removing stored scrapes", scrape_id)
        with suppress(ScrapeStoreError):
            self._call_store("clear", lambda: self._collection.delete_many({}))

    def _replace_all_reports(self, report_document: dict[str, Any]) -> None:
        scrape_id = report_document["_id"]
        self._collection.replace_one({"_id": scrape_id}, report_document, upsert=True)
        self._collection.delete_many({"_id": {"$ne": scrape_id}})

    def _call_store(self, action: str, operation: Callable[[], OperationValue]) -> OperationValue:
        if self._clock() < self._paused_until:
            raise ScrapeStoreUnavailableError("scrape storage is paused after a failure")
        try:
            return operation()
        except UNAVAILABLE_ERRORS as exc:
            self._pause_store(action, exc)
            raise ScrapeStoreUnavailableError(str(exc)) from exc
        except STORE_ERRORS as exc:
            LOG.warning("ui_runs %s failed: %s", action, exc)
            raise ScrapeStoreError(str(exc)) from exc

    def _pause_store(self, action: str, exc: Exception) -> None:
        self._paused_until = self._clock() + self._breaker_seconds
        LOG.warning(
            "ui_runs %s failed, skipping scrape storage for %d s, scrape results stay in memory: %s",
            action,
            self._breaker_seconds,
            exc,
        )


def open_scrape_report_repository() -> MongoScrapeReportRepository:
    mongo_uri = os.environ.get("MONGO_URI", DEFAULT_MONGO_URI)
    database_name = os.environ.get("MONGO_DB_NAME", DEFAULT_DB_NAME)
    client: Any = MongoClient(
        mongo_uri,
        serverSelectionTimeoutMS=SCRAPE_STORE_TIMEOUT_MS,
        connectTimeoutMS=SCRAPE_STORE_TIMEOUT_MS,
    )
    return MongoScrapeReportRepository(client[database_name])


def _read_report_or_none(document: dict[str, Any] | None) -> ScrapeReport | None:
    if document is None:
        return None
    try:
        return read_report_from_document(document)
    except UNREADABLE_ERRORS as exc:
        LOG.warning("unreadable ui_runs document %s: %r", document.get("_id"), exc)
        return None


def _read_current_time_text() -> str:
    return datetime.now(UTC).isoformat()


def _build_report_document(scrape_report: ScrapeReport) -> dict[str, Any]:
    report_document = convert_report_to_document(scrape_report)
    report_document["_id"] = scrape_report.summary.id
    report_document["saved_at"] = _read_current_time_text()
    return report_document


def _measure_document_size(report_document: dict[str, Any]) -> str:
    try:
        return str(len(bson.encode(report_document)))
    except (BSONError, TypeError, ValueError):
        return "unknown"


def _build_summary_upsert(scrape_summary: ScrapeSummary) -> dict[str, Any]:
    empty_report_fields = {
        "jobs": [],
        "failures": [],
        "payloads": [],
        "saved_at": _read_current_time_text(),
    }
    return {
        "$set": {"record": convert_summary_to_dict(scrape_summary)},
        "$setOnInsert": empty_report_fields,
    }
