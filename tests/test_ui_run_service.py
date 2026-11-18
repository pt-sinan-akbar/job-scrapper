from __future__ import annotations

import asyncio
import logging
from typing import Any

import mongomock
import pytest
from pymongo import MongoClient

from ui_server.errors import (
    ConfigInvalidError,
    DiscordForbiddenError,
    DiscordNotConfiguredError,
    DiscordUnauthorizedError,
    McpUnavailableError,
    RunInProgressError,
    RunNotFoundError,
    RunStorageUnavailableError,
)
from ui_server.services.run_record import DiscordStatus, RunStatus
from ui_server.services.run_repository import UI_RUNS_COLLECTION, MongoRunRepository
from ui_server.services.run_service import RunService

CHANNEL_ID = "123456789012345678"
USER_ID = "223456789012345678"
DISCORD_SETTINGS = {
    "configured": True,
    "default_channel_id": CHANNEL_ID,
    "mention_user_id": USER_ID,
}


class FakeScraper:
    def __init__(self, outcome: dict | Exception) -> None:
        self._outcome = outcome
        self.release = asyncio.Event()
        self.settings: dict | Exception = DISCORD_SETTINGS
        self.send_outcomes: list[dict | Exception] = []
        self.sent_messages: list[tuple] = []

    async def scrape_jobs(self, sites: tuple[str, ...], keywords: tuple[str, ...]) -> dict:
        await self.release.wait()
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome

    async def read_discord_settings(self) -> dict:
        if isinstance(self.settings, Exception):
            raise self.settings
        return self.settings

    async def send_discord_message(
        self, channel_id: str, mention: bool, text: str | None, jobs: list[dict] | None
    ) -> dict:
        self.sent_messages.append((channel_id, mention, text, jobs))
        outcome = self.send_outcomes.pop(0) if self.send_outcomes else _default_delivery(text, jobs)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _entry(kind: str, status: str) -> dict:
    return {"index": 0, "kind": kind, "title": None, "status": status, "message_id": None}


def _delivery(sent: int, failed: int, summary_status: str = "sent") -> dict:
    results = [
        *[_entry("job", "sent")] * sent,
        *[_entry("job", "failed")] * failed,
        _entry("summary", summary_status),
    ]
    summary_failed = summary_status == "failed"
    return {
        "sent": sent + (0 if summary_failed else 1),
        "failed": failed + (1 if summary_failed else 0),
        "results": results,
    }


def _text_delivery(status: str) -> dict:
    return {
        "sent": int(status == "sent"),
        "failed": int(status == "failed"),
        "results": [_entry("text", status)],
    }


def _default_delivery(text: str | None, jobs: list[dict] | None) -> dict:
    if text is not None:
        return _text_delivery("sent")
    return _delivery(len(jobs or []), 0)


def _jobs_result(count: int) -> dict:
    jobs = [{"title": f"job {index}"} for index in range(count)]
    return {
        "ok": True,
        "results": [{"keyword": "django", "sites": [{"site": "upwork", "jobs": jobs}]}],
        "errors": [],
    }


def _database() -> Any:
    return mongomock.MongoClient()["job_scraper"]


def _service(scraper: FakeScraper, database: Any = None) -> RunService:
    return RunService(scraper, MongoRunRepository(_database() if database is None else database))


def test_run_finishes_and_saves_result():
    async def scenario() -> RunStatus:
        scraper = FakeScraper({"ok": True, "results": [], "errors": []})
        service = _service(scraper)
        record = service.start(("django",), ("upwork",), notify_discord=False)
        scraper.release.set()
        await service.wait()
        return service.get(record.id).record.status

    assert asyncio.run(scenario()) is RunStatus.SUCCEEDED


def test_second_run_is_refused_while_first_is_active():
    async def scenario() -> None:
        scraper = FakeScraper({"ok": True})
        service = _service(scraper)
        service.start(("django",), ("upwork",), notify_discord=False)
        with pytest.raises(RunInProgressError):
            service.start(("flask",), ("upwork",), notify_discord=False)
        scraper.release.set()
        await service.wait()

    asyncio.run(scenario())


def test_new_run_replaces_the_previous_record():
    async def scenario() -> None:
        scraper = FakeScraper({"ok": True})
        service = _service(scraper)
        scraper.release.set()
        first = service.start(("django",), ("upwork",), notify_discord=False)
        await service.wait()
        second = service.start(("flask",), ("upwork",), notify_discord=False)
        await service.wait()
        with pytest.raises(RunNotFoundError):
            service.get(first.id)
        assert service.get(second.id).record.keywords == ("flask",)

    asyncio.run(scenario())


def test_get_returns_running_record_before_finish():
    async def scenario() -> RunStatus:
        scraper = FakeScraper({"ok": True})
        service = _service(scraper)
        record = service.start(("django",), ("upwork",), notify_discord=False)
        status = service.get(record.id).record.status
        scraper.release.set()
        await service.wait()
        return status

    assert asyncio.run(scenario()) is RunStatus.RUNNING


def test_get_before_any_run_raises_not_found():
    service = _service(FakeScraper({"ok": True}))

    with pytest.raises(RunNotFoundError):
        service.get("20261101T010000Z-abc123")


def test_get_unknown_id_raises_not_found():
    async def scenario() -> None:
        scraper = FakeScraper({"ok": True})
        service = _service(scraper)
        scraper.release.set()
        service.start(("django",), ("upwork",), notify_discord=False)
        await service.wait()
        with pytest.raises(RunNotFoundError):
            service.get("nope")

    asyncio.run(scenario())


def test_finished_run_counts_jobs_and_errors():
    async def scenario():
        result = {**_jobs_result(3), "ok": False, "errors": [{"site": "x"}]}
        scraper = FakeScraper(result)
        service = _service(scraper)
        record = service.start(("django",), ("upwork",), notify_discord=False)
        scraper.release.set()
        await service.wait()
        return service.get(record.id).record

    record = asyncio.run(scenario())

    assert record.status is RunStatus.PARTIAL
    assert (record.job_count, record.error_count) == (3, 1)
    assert record.finished_at is not None


def test_mcp_failure_marks_run_failed():
    async def scenario() -> str | None:
        scraper = FakeScraper(McpUnavailableError("MCP down"))
        service = _service(scraper)
        record = service.start(("django",), ("upwork",), notify_discord=False)
        scraper.release.set()
        await service.wait()
        return service.get(record.id).record.error

    assert asyncio.run(scenario()) == "MCP down"


def test_unexpected_failure_hides_detail():
    async def scenario() -> str | None:
        scraper = FakeScraper(RuntimeError("secret detail"))
        service = _service(scraper)
        record = service.start(("django",), ("upwork",), notify_discord=False)
        scraper.release.set()
        await service.wait()
        return service.get(record.id).record.error

    assert asyncio.run(scenario()) == "The scrape failed."


def _notified_run(scraper: FakeScraper):
    async def scenario():
        service = _service(scraper)
        record = service.start(("django",), ("upwork",), notify_discord=True)
        scraper.release.set()
        await service.wait()
        return service.get(record.id).record

    return asyncio.run(scenario())


def test_run_without_notify_never_touches_discord():
    scraper = FakeScraper(_jobs_result(2))

    async def scenario():
        service = _service(scraper)
        record = service.start(("django",), ("upwork",), notify_discord=False)
        scraper.release.set()
        await service.wait()
        return service.get(record.id).record

    record = asyncio.run(scenario())

    assert record.discord_status is None
    assert scraper.sent_messages == []


def test_notify_sends_all_jobs_to_default_channel_with_mention():
    scraper = FakeScraper(_jobs_result(2))
    scraper.send_outcomes = [_delivery(2, 0)]

    record = _notified_run(scraper)

    assert scraper.sent_messages == [
        (CHANNEL_ID, True, None, [{"title": "job 0"}, {"title": "job 1"}])
    ]
    assert record.status is RunStatus.SUCCEEDED
    assert record.discord_status is DiscordStatus.SENT
    assert (record.discord_sent, record.discord_failed, record.discord_error) == (2, 0, None)


def test_notify_without_mention_user_sends_without_mention():
    scraper = FakeScraper(_jobs_result(1))
    scraper.settings = {**DISCORD_SETTINGS, "mention_user_id": None}

    _notified_run(scraper)

    assert scraper.sent_messages[0][1] is False


def test_notify_splits_jobs_in_chunks_of_fifty():
    scraper = FakeScraper(_jobs_result(120))
    scraper.send_outcomes = [_delivery(50, 0), _delivery(48, 2), _delivery(20, 0)]

    record = _notified_run(scraper)

    assert [len(message[3]) for message in scraper.sent_messages] == [50, 50, 20]
    assert (record.discord_sent, record.discord_failed) == (118, 2)
    assert record.discord_status is DiscordStatus.PARTIAL


def test_notify_counts_only_job_messages_not_the_summary():
    scraper = FakeScraper(_jobs_result(100))
    scraper.send_outcomes = [_delivery(50, 0), _delivery(50, 0)]

    record = _notified_run(scraper)

    assert (record.discord_sent, record.discord_failed) == (100, 0)
    assert record.discord_status is DiscordStatus.SENT


def test_notify_ignores_a_failed_summary_message():
    scraper = FakeScraper(_jobs_result(2))
    scraper.send_outcomes = [_delivery(2, 0, summary_status="failed")]

    record = _notified_run(scraper)

    assert (record.discord_sent, record.discord_failed) == (2, 0)
    assert record.discord_status is DiscordStatus.SENT


def test_notify_with_failed_text_message_is_failed():
    scraper = FakeScraper(_jobs_result(0))
    scraper.send_outcomes = [_text_delivery("failed")]

    record = _notified_run(scraper)

    assert (record.discord_sent, record.discord_failed) == (0, 1)
    assert record.discord_status is DiscordStatus.FAILED


def test_notify_mentions_only_on_the_first_chunk():
    scraper = FakeScraper(_jobs_result(120))

    _notified_run(scraper)

    assert [message[1] for message in scraper.sent_messages] == [True, False, False]


def test_notify_keeps_counts_when_a_later_chunk_raises():
    scraper = FakeScraper(_jobs_result(120))
    scraper.send_outcomes = [_delivery(50, 0), DiscordForbiddenError()]

    record = _notified_run(scraper)

    assert len(scraper.sent_messages) == 2
    assert record.discord_status is DiscordStatus.PARTIAL
    assert (record.discord_sent, record.discord_failed) == (50, 0)
    assert record.discord_error == DiscordForbiddenError.default_message


def test_notify_with_first_chunk_raising_is_failed():
    scraper = FakeScraper(_jobs_result(120))
    scraper.send_outcomes = [DiscordUnauthorizedError()]

    record = _notified_run(scraper)

    assert len(scraper.sent_messages) == 1
    assert record.discord_status is DiscordStatus.FAILED
    assert (record.discord_sent, record.discord_failed) == (0, 0)
    assert record.discord_error == DiscordUnauthorizedError.default_message


@pytest.mark.parametrize(
    "error",
    [
        DiscordNotConfiguredError(),
        DiscordUnauthorizedError(),
        DiscordForbiddenError(),
        ConfigInvalidError("text is too long"),
        McpUnavailableError("MCP down"),
    ],
)
def test_notify_maps_known_errors_to_their_message(error: Exception):
    scraper = FakeScraper(_jobs_result(1))
    scraper.send_outcomes = [error]

    record = _notified_run(scraper)

    assert record.discord_error == str(error)


def test_notify_unknown_error_after_partial_keeps_generic_message():
    scraper = FakeScraper(_jobs_result(120))
    scraper.send_outcomes = [_delivery(50, 0), RuntimeError("secret detail")]

    record = _notified_run(scraper)

    assert record.discord_status is DiscordStatus.PARTIAL
    assert record.discord_error == "Sending to Discord failed."
    assert record.discord_sent == 50


def test_notify_text_with_long_keywords_fits_with_mention_prefix():
    async def scenario() -> list[tuple]:
        scraper = FakeScraper(McpUnavailableError("MCP down"))
        service = _service(scraper)
        service.start(("k" * 3000,), ("upwork",), notify_discord=True)
        scraper.release.set()
        await service.wait()
        return scraper.sent_messages

    text = asyncio.run(scenario())[0][2]

    assert len(f"<@{USER_ID}>\n{text}") <= 2000
    assert text.endswith(": MCP down")


def test_notify_text_without_overflow_is_unchanged():
    scraper = FakeScraper(McpUnavailableError("MCP down"))

    _notified_run(scraper)

    assert scraper.sent_messages[0][2] == "Run failed for django on upwork: MCP down"


def test_notify_with_every_message_failed_is_failed():
    scraper = FakeScraper(_jobs_result(2))
    scraper.send_outcomes = [_delivery(0, 2)]

    record = _notified_run(scraper)

    assert record.discord_status is DiscordStatus.FAILED
    assert (record.discord_sent, record.discord_failed) == (0, 2)


def test_notify_with_zero_jobs_sends_one_text_message():
    scraper = FakeScraper(_jobs_result(0))

    record = _notified_run(scraper)

    assert scraper.sent_messages == [(CHANNEL_ID, True, "django on upwork found 0 jobs", None)]
    assert record.discord_status is DiscordStatus.SENT


def test_notify_after_failed_run_sends_failure_text():
    scraper = FakeScraper(McpUnavailableError("MCP down"))

    record = _notified_run(scraper)

    assert scraper.sent_messages == [
        (CHANNEL_ID, True, "Run failed for django on upwork: MCP down", None)
    ]
    assert record.status is RunStatus.FAILED
    assert record.discord_status is DiscordStatus.SENT


def test_notify_after_unexpected_failure_hides_detail_in_text():
    scraper = FakeScraper(RuntimeError("secret detail"))

    _notified_run(scraper)

    assert scraper.sent_messages[0][2] == "Run failed for django on upwork: The scrape failed."


def test_notify_without_token_fails_and_sends_nothing():
    scraper = FakeScraper(_jobs_result(1))
    scraper.settings = {**DISCORD_SETTINGS, "configured": False}

    record = _notified_run(scraper)

    assert scraper.sent_messages == []
    assert record.discord_status is DiscordStatus.FAILED
    assert record.discord_error == "Discord token is not configured."
    assert record.status is RunStatus.SUCCEEDED


def test_notify_without_default_channel_fails_and_sends_nothing():
    scraper = FakeScraper(_jobs_result(1))
    scraper.settings = {**DISCORD_SETTINGS, "default_channel_id": None}

    record = _notified_run(scraper)

    assert scraper.sent_messages == []
    assert record.discord_status is DiscordStatus.FAILED
    assert record.discord_error == "No default Discord channel is set."


def test_notify_send_error_hides_detail():
    scraper = FakeScraper(_jobs_result(1))
    scraper.send_outcomes = [RuntimeError("secret detail")]

    record = _notified_run(scraper)

    assert record.discord_status is DiscordStatus.FAILED
    assert record.discord_error == "Sending to Discord failed."
    assert record.status is RunStatus.SUCCEEDED


def test_notify_settings_error_marks_discord_failed():
    scraper = FakeScraper(_jobs_result(1))
    scraper.settings = McpUnavailableError("MCP down")

    record = _notified_run(scraper)

    assert record.discord_status is DiscordStatus.FAILED
    assert record.discord_error == "Sending to Discord failed."


def test_run_stays_busy_while_discord_is_sending():
    async def scenario() -> tuple[DiscordStatus | None, bool]:
        scraper = FakeScraper(_jobs_result(1))
        gate = asyncio.Event()
        original = scraper.send_discord_message

        async def slow_send(*arguments):
            await gate.wait()
            return await original(*arguments)

        scraper.send_discord_message = slow_send
        service = _service(scraper)
        record = service.start(("django",), ("upwork",), notify_discord=True)
        scraper.release.set()
        for _ in range(20):
            await asyncio.sleep(0)
        current = service.get(record.id).record
        is_busy = False
        try:
            service.ensure_idle()
        except RunInProgressError:
            is_busy = True
        gate.set()
        await service.wait()
        return current.discord_status, is_busy

    assert asyncio.run(scenario()) == (DiscordStatus.SENDING, True)


def _payload_result() -> dict:
    return {
        **_jobs_result(1),
        "ok": False,
        "errors": [{"keyword": "django", "site": "glints", "reason": "timeout"}],
        "raw_results": [{"keyword": "django", "site": "upwork", "payload": {"jobs": [1]}}],
        "filtered_results": [{"keyword": "django", "site": "upwork", "payload": {"jobs": []}}],
    }


def _finished(scraper: FakeScraper, database: Any, notify_discord: bool = False):
    async def scenario():
        service = _service(scraper, database)
        record = service.start(("django",), ("upwork",), notify_discord=notify_discord)
        scraper.release.set()
        await service.wait()
        return service, record

    return asyncio.run(scenario())


def test_running_detail_has_empty_lists():
    async def scenario():
        scraper = FakeScraper(_jobs_result(1))
        service = _service(scraper)
        record = service.start(("django",), ("upwork",), notify_discord=False)
        detail = service.get(record.id)
        scraper.release.set()
        await service.wait()
        return detail

    detail = asyncio.run(scenario())

    assert detail.record.status is RunStatus.RUNNING
    assert (detail.jobs, detail.failures, detail.payloads) == ((), (), ())


def test_finished_run_detail_has_jobs_failures_and_payloads():
    service, record = _finished(FakeScraper(_payload_result()), _database())

    detail = service.get(record.id)

    assert detail.jobs[0]["title"] == "job 0"
    assert detail.jobs[0]["site"] == "upwork"
    assert detail.jobs[0]["matched_keyword"] == "django"
    assert detail.failures == ({"keyword": "django", "site": "glints", "reason": "timeout"},)
    assert detail.payloads == (
        {"keyword": "django", "site": "upwork", "raw": {"jobs": [1]}, "filtered": {"jobs": []}},
    )


def test_finished_run_is_saved_to_ui_runs():
    database = _database()

    service, record = _finished(FakeScraper(_payload_result()), database)

    document = database[UI_RUNS_COLLECTION].find_one({"_id": record.id})
    assert document["record"]["status"] == "partial"
    assert document["jobs"][0]["title"] == "job 0"
    assert document["failures"] == [{"keyword": "django", "site": "glints", "reason": "timeout"}]
    assert document["payloads"][0]["raw"] == {"jobs": [1]}


def test_failed_run_is_saved_with_empty_lists():
    database = _database()

    _, record = _finished(FakeScraper(McpUnavailableError("MCP down")), database)

    document = database[UI_RUNS_COLLECTION].find_one({"_id": record.id})
    assert document["record"]["status"] == "failed"
    assert document["record"]["error"] == "MCP down"
    assert (document["jobs"], document["failures"], document["payloads"]) == ([], [], [])


def test_scrape_runs_collection_is_never_written():
    database = _database()

    _finished(FakeScraper(_payload_result()), database)

    assert "scrape_runs" not in database.list_collection_names()


def test_only_the_latest_run_stays_in_ui_runs():
    async def scenario(database: Any) -> tuple[str, str]:
        scraper = FakeScraper(_jobs_result(1))
        service = _service(scraper, database)
        scraper.release.set()
        first = service.start(("django",), ("upwork",), notify_discord=False)
        await service.wait()
        second = service.start(("flask",), ("upwork",), notify_discord=False)
        await service.wait()
        return first.id, second.id

    database = _database()
    _, second_id = asyncio.run(scenario(database))

    ids = [document["_id"] for document in database[UI_RUNS_COLLECTION].find()]
    assert ids == [second_id]


def test_discord_status_is_saved_to_the_stored_record():
    database = _database()
    scraper = FakeScraper(_jobs_result(2))
    scraper.send_outcomes = [_delivery(2, 0)]

    _, record = _finished(scraper, database, notify_discord=True)

    stored = database[UI_RUNS_COLLECTION].find_one({"_id": record.id})["record"]
    assert stored["discord_status"] == "sent"
    assert (stored["discord_sent"], stored["discord_failed"]) == (2, 0)
    assert stored["status"] == "succeeded"


def test_discord_failure_is_saved_to_the_stored_record():
    database = _database()
    scraper = FakeScraper(_jobs_result(1))
    scraper.settings = {**DISCORD_SETTINGS, "configured": False}

    _, record = _finished(scraper, database, notify_discord=True)

    stored = database[UI_RUNS_COLLECTION].find_one({"_id": record.id})["record"]
    assert stored["discord_status"] == "failed"
    assert stored["discord_error"] == "Discord token is not configured."


def test_new_service_reads_the_stored_run():
    database = _database()
    _, record = _finished(FakeScraper(_payload_result()), database)

    fresh = _service(FakeScraper({"ok": True}), database)

    assert fresh.latest().record.id == record.id
    assert fresh.get(record.id).jobs[0]["title"] == "job 0"


def test_latest_without_any_run_is_none():
    assert _service(FakeScraper({"ok": True})).latest() is None


def test_latest_prefers_the_current_run_over_the_stored_one():
    async def scenario(database: Any, old_id: str):
        scraper = FakeScraper(_jobs_result(1))
        service = _service(scraper, database)
        record = service.start(("flask",), ("upwork",), notify_discord=False)
        latest = service.latest()
        stored = service.get(old_id)
        scraper.release.set()
        await service.wait()
        return record, latest, stored

    database = _database()
    _, old = _finished(FakeScraper(_jobs_result(1)), database)
    record, latest, stored = asyncio.run(scenario(database, old.id))

    assert latest.record.id == record.id
    assert latest.record.status is RunStatus.RUNNING
    assert stored.record.id == old.id


def test_run_works_from_memory_when_mongo_is_down(caplog: pytest.LogCaptureFixture):
    client: Any = MongoClient("mongodb://127.0.0.1:1", serverSelectionTimeoutMS=50)
    scraper = FakeScraper(_payload_result())
    scraper.send_outcomes = [_delivery(1, 0)]

    with caplog.at_level(logging.WARNING, logger="scraper-ui"):
        service, record = _finished(scraper, client["job_scraper"], notify_discord=True)

    detail = service.get(record.id)
    assert detail.record.status is RunStatus.PARTIAL
    assert detail.record.discord_status is DiscordStatus.SENT
    assert detail.jobs[0]["title"] == "job 0"
    assert service.latest() == detail
    assert "ui_runs" in caplog.text
    with pytest.raises(RunStorageUnavailableError):
        service.get("20261101T010000Z-abc123")


def test_storage_unavailable_error_is_503_with_a_clear_message():
    error = RunStorageUnavailableError()

    assert error.status_code == 503
    assert error.message == "Run storage is unavailable."


def test_latest_is_none_when_mongo_is_down_and_nothing_is_in_memory():
    client: Any = MongoClient("mongodb://127.0.0.1:1", serverSelectionTimeoutMS=50)

    assert _service(FakeScraper({"ok": True}), client["job_scraper"]).latest() is None


@pytest.mark.parametrize(
    "result",
    [
        {"ok": True, "results": [None], "errors": []},
        {"ok": True, "results": "garbage", "errors": []},
        {"ok": True, "results": [{"keyword": "django", "sites": [{"jobs": 5}]}], "errors": []},
        {"ok": True, "results": [], "errors": 7},
    ],
)
def test_malformed_result_fails_the_run_with_the_generic_message(result: dict):
    async def scenario(database: Any):
        scraper = FakeScraper(result)
        service = _service(scraper, database)
        record = service.start(("django",), ("upwork",), notify_discord=False)
        scraper.release.set()
        await service.wait()
        service.ensure_idle()
        return service.get(record.id).record

    database = _database()
    record = asyncio.run(scenario(database))

    assert record.status is RunStatus.FAILED
    assert record.error == "The scrape failed."
    assert record.finished_at is not None
    stored = database[UI_RUNS_COLLECTION].find_one({"_id": record.id})
    assert stored["record"]["status"] == "failed"


def test_malformed_result_still_reports_the_failure_to_discord():
    scraper = FakeScraper({"ok": True, "results": [None], "errors": []})

    record = _notified_run(scraper)

    assert record.status is RunStatus.FAILED
    assert record.discord_status is DiscordStatus.SENT
    assert "The scrape failed." in scraper.sent_messages[0][2]


class _BrokenSaveRepository(MongoRunRepository):
    def save(self, detail: Any) -> None:
        raise RuntimeError("boom")


def test_run_ends_with_a_terminal_status_when_saving_crashes():
    async def scenario():
        scraper = FakeScraper(_jobs_result(1))
        service = RunService(scraper, _BrokenSaveRepository(_database()))
        service.start(("django",), ("upwork",), notify_discord=False)
        scraper.release.set()
        await service.wait()
        service.ensure_idle()
        return service.latest()

    detail = asyncio.run(scenario())

    assert detail.record.status is not RunStatus.RUNNING
