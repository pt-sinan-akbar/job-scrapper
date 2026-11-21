from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import pymongo
import pytest

from backend.services import scrape_report_repository
from mcp_server import server as mcp_server_module
from scraper import job_settings
from scraper.sites import _location

_MODULES_HOLDING_THE_MONGO_CLIENT_CLASS = (
    pymongo,
    job_settings,
    _location,
    scrape_report_repository,
)
_REAL_MONGO_REFUSED_MESSAGE = "a test tried to open a real Mongo connection"


@pytest.fixture(autouse=True)
def _location_index_never_reads_real_mongo(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    _location.clear_cached_location_index()
    monkeypatch.setattr(_location, "_load_wilayah_index_from_mongo", lambda: None)
    yield
    _location.clear_cached_location_index()


@pytest.fixture(autouse=True)
def _no_test_opens_a_real_mongo_connection(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    refused_connection_targets: list[str] = []

    def refuse_real_mongo_connection(*args: object, **kwargs: object) -> None:
        refused_connection_targets.append(_describe_connection_target(args, kwargs))
        pytest.fail(_REAL_MONGO_REFUSED_MESSAGE)

    for module in _MODULES_HOLDING_THE_MONGO_CLIENT_CLASS:
        monkeypatch.setattr(module, "MongoClient", refuse_real_mongo_connection)
    yield
    if refused_connection_targets:
        pytest.fail(f"{_REAL_MONGO_REFUSED_MESSAGE}: {refused_connection_targets}")


@pytest.fixture(autouse=True)
def _status_file_is_written_only_inside_tmp_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    isolated_status_path = tmp_path / "isolated_status" / "status.json"
    monkeypatch.setattr(mcp_server_module, "_STATUS_PATH", isolated_status_path)


@pytest.fixture
def scraper_log_records(caplog: pytest.LogCaptureFixture) -> Iterator[pytest.LogCaptureFixture]:
    scraper_logger = logging.getLogger("job-scraper")
    scraper_logger.addHandler(caplog.handler)
    yield caplog
    scraper_logger.removeHandler(caplog.handler)


def _describe_connection_target(args: tuple[object, ...], kwargs: dict[str, object]) -> str:
    if args:
        return str(args[0])
    return str(kwargs.get("host", "default host"))
