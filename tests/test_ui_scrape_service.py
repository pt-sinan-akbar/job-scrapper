from __future__ import annotations

import asyncio
import logging
from typing import Any

import mongomock
import pytest
from pymongo import MongoClient

from backend.errors import (
    ConfigInvalidError,
    DiscordForbiddenError,
    DiscordNotConfiguredError,
    DiscordUnauthorizedError,
    McpUnavailableError,
    ScrapeInProgressError,
    ScrapeNotFoundError,
    ScrapeNotSendableError,
    ScrapeStorageUnavailableError,
)
from backend.services.scrape_report import ScrapeReport
from backend.services.scrape_report_repository import (
    SCRAPE_REPORTS_COLLECTION,
    MongoScrapeReportRepository,
)
from backend.services.scrape_service import ScrapeService
from backend.services.scrape_summary import DiscordStatus, ScrapeStatus

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
        self.sent_digest_counts: list[dict | None] = []
        self.scraped_locations: list[str | None] = []
        self.scraped_max_age_hours: list[int | None] = []

    async def scrape_jobs(
        self,
        sites: tuple[str, ...],
        keywords: tuple[str, ...],
        location: str | None = None,
        max_age_hours: int | None = None,
    ) -> dict:
        self.scraped_locations.append(location)
        self.scraped_max_age_hours.append(max_age_hours)
        await self.release.wait()
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome

    async def read_discord_settings(self) -> dict:
        if isinstance(self.settings, Exception):
            raise self.settings
        return self.settings

    async def send_discord_message(
        self,
        channel_id: str,
        mention: bool,
        text: str | None,
        jobs: list[dict] | None,
        digest_counts: dict | None = None,
    ) -> dict:
        self.sent_messages.append((channel_id, mention, text, jobs))
        self.sent_digest_counts.append(digest_counts)
        outcome = self.send_outcomes.pop(0) if self.send_outcomes else _default_delivery(text, jobs)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _entry(kind: str, status: str, job_count: int = 0) -> dict:
    return {
        "index": 0,
        "kind": kind,
        "title": None,
        "job_count": job_count,
        "status": status,
        "message_id": None,
    }


def _file_delivery(job_count: int, status: str = "sent") -> dict:
    return {
        "sent": int(status == "sent"),
        "failed": int(status == "failed"),
        "results": [_entry("file", status, job_count)],
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
    return _file_delivery(len(jobs or []))


def _jobs_result(count: int) -> dict:
    jobs = [{"title": f"job {index}"} for index in range(count)]
    return {
        "ok": True,
        "results": [{"keyword": "django", "site": "upwork", "payload": {"jobs": jobs}}],
        "errors": [],
    }


def _job_view(index: int) -> dict:
    return {
        "site": "upwork",
        "matched_keyword": "django",
        "title": f"job {index}",
        "company": None,
        "location": None,
        "url": None,
        "posted_at": None,
    }


def _database() -> Any:
    return mongomock.MongoClient()["job_scraper"]


def _service(scraper: FakeScraper, database: Any = None) -> ScrapeService:
    return ScrapeService(
        scraper, MongoScrapeReportRepository(_database() if database is None else database)
    )


def _read_latest_report(service: ScrapeService) -> ScrapeReport:
    latest_report = service.read_latest_scrape_report()
    assert latest_report is not None
    return latest_report


def test_scrape_finishes_and_saves_result():
    async def scenario() -> ScrapeStatus:
        scraper = FakeScraper({"ok": True, "results": [], "errors": []})
        service = _service(scraper)
        scrape_summary = service.start_scrape(("django",), ("upwork",), notify_discord=False)
        scraper.release.set()
        await service.wait_for_current_task()
        return service.read_scrape_report(scrape_summary.id).summary.status

    assert asyncio.run(scenario()) is ScrapeStatus.SUCCEEDED


def test_scrape_sends_the_requested_location_and_keeps_it_on_the_summary():
    async def scenario() -> tuple[str | None, list[str | None]]:
        scraper = FakeScraper({"ok": True, "results": [], "errors": []})
        service = _service(scraper)
        scrape_summary = service.start_scrape(
            ("django",), ("upwork",), notify_discord=False, location="Jakarta"
        )
        scraper.release.set()
        await service.wait_for_current_task()
        stored_location = service.read_scrape_report(scrape_summary.id).summary.location
        return stored_location, scraper.scraped_locations

    assert asyncio.run(scenario()) == ("Jakarta", ["Jakarta"])


def test_scrape_without_location_sends_none_and_keeps_none_on_the_summary():
    async def scenario() -> tuple[str | None, list[str | None]]:
        scraper = FakeScraper({"ok": True, "results": [], "errors": []})
        service = _service(scraper)
        scrape_summary = service.start_scrape(("django",), ("upwork",), notify_discord=False)
        scraper.release.set()
        await service.wait_for_current_task()
        stored_location = service.read_scrape_report(scrape_summary.id).summary.location
        return stored_location, scraper.scraped_locations

    assert asyncio.run(scenario()) == (None, [None])


def test_scrape_sends_the_requested_max_age_and_keeps_it_on_the_summary():
    async def scenario() -> tuple[int | None, list[int | None]]:
        scraper = FakeScraper({"ok": True, "results": [], "errors": []})
        service = _service(scraper)
        scrape_summary = service.start_scrape(
            ("django",), ("upwork",), notify_discord=False, max_age_hours=168
        )
        scraper.release.set()
        await service.wait_for_current_task()
        stored_max_age_hours = service.read_scrape_report(scrape_summary.id).summary.max_age_hours
        return stored_max_age_hours, scraper.scraped_max_age_hours

    assert asyncio.run(scenario()) == (168, [168])


def test_scrape_without_max_age_sends_none_and_keeps_none_on_the_summary():
    async def scenario() -> tuple[int | None, list[int | None]]:
        scraper = FakeScraper({"ok": True, "results": [], "errors": []})
        service = _service(scraper)
        scrape_summary = service.start_scrape(("django",), ("upwork",), notify_discord=False)
        scraper.release.set()
        await service.wait_for_current_task()
        stored_max_age_hours = service.read_scrape_report(scrape_summary.id).summary.max_age_hours
        return stored_max_age_hours, scraper.scraped_max_age_hours

    assert asyncio.run(scenario()) == (None, [None])


def test_second_scrape_is_refused_while_first_is_active():
    async def scenario() -> None:
        scraper = FakeScraper({"ok": True})
        service = _service(scraper)
        service.start_scrape(("django",), ("upwork",), notify_discord=False)
        with pytest.raises(ScrapeInProgressError):
            service.start_scrape(("flask",), ("upwork",), notify_discord=False)
        scraper.release.set()
        await service.wait_for_current_task()

    asyncio.run(scenario())


def test_new_scrape_replaces_the_previous_record():
    async def scenario() -> None:
        scraper = FakeScraper({"ok": True})
        service = _service(scraper)
        scraper.release.set()
        first = service.start_scrape(("django",), ("upwork",), notify_discord=False)
        await service.wait_for_current_task()
        second = service.start_scrape(("flask",), ("upwork",), notify_discord=False)
        await service.wait_for_current_task()
        with pytest.raises(ScrapeNotFoundError):
            service.read_scrape_report(first.id)
        assert service.read_scrape_report(second.id).summary.keywords == ("flask",)

    asyncio.run(scenario())


def test_get_returns_running_record_before_finish():
    async def scenario() -> ScrapeStatus:
        scraper = FakeScraper({"ok": True})
        service = _service(scraper)
        scrape_summary = service.start_scrape(("django",), ("upwork",), notify_discord=False)
        status = service.read_scrape_report(scrape_summary.id).summary.status
        scraper.release.set()
        await service.wait_for_current_task()
        return status

    assert asyncio.run(scenario()) is ScrapeStatus.RUNNING


def test_get_before_any_scrape_raises_not_found():
    service = _service(FakeScraper({"ok": True}))

    with pytest.raises(ScrapeNotFoundError):
        service.read_scrape_report("20261101T010000Z-abc123")


def test_get_unknown_id_raises_not_found():
    async def scenario() -> None:
        scraper = FakeScraper({"ok": True})
        service = _service(scraper)
        scraper.release.set()
        service.start_scrape(("django",), ("upwork",), notify_discord=False)
        await service.wait_for_current_task()
        with pytest.raises(ScrapeNotFoundError):
            service.read_scrape_report("nope")

    asyncio.run(scenario())


def test_finished_scrape_counts_jobs_and_errors():
    async def scenario():
        result = {**_jobs_result(3), "ok": False, "errors": [{"site": "x"}]}
        scraper = FakeScraper(result)
        service = _service(scraper)
        scrape_summary = service.start_scrape(("django",), ("upwork",), notify_discord=False)
        scraper.release.set()
        await service.wait_for_current_task()
        return service.read_scrape_report(scrape_summary.id).summary

    scrape_summary = asyncio.run(scenario())

    assert scrape_summary.status is ScrapeStatus.PARTIAL
    assert (scrape_summary.job_count, scrape_summary.error_count) == (3, 1)
    assert scrape_summary.finished_at is not None


def test_mcp_failure_marks_scrape_failed():
    async def scenario() -> str | None:
        scraper = FakeScraper(McpUnavailableError("MCP down"))
        service = _service(scraper)
        scrape_summary = service.start_scrape(("django",), ("upwork",), notify_discord=False)
        scraper.release.set()
        await service.wait_for_current_task()
        return service.read_scrape_report(scrape_summary.id).summary.error

    assert asyncio.run(scenario()) == "MCP down"


def test_unexpected_failure_hides_the_error_text():
    async def scenario() -> str | None:
        scraper = FakeScraper(RuntimeError("secret detail"))
        service = _service(scraper)
        scrape_summary = service.start_scrape(("django",), ("upwork",), notify_discord=False)
        scraper.release.set()
        await service.wait_for_current_task()
        return service.read_scrape_report(scrape_summary.id).summary.error

    assert asyncio.run(scenario()) == "The scrape failed."


def _notified_scrape(scraper: FakeScraper):
    async def scenario():
        service = _service(scraper)
        scrape_summary = service.start_scrape(("django",), ("upwork",), notify_discord=True)
        scraper.release.set()
        await service.wait_for_current_task()
        return service.read_scrape_report(scrape_summary.id).summary

    return asyncio.run(scenario())


def test_scrape_without_notify_never_touches_discord():
    scraper = FakeScraper(_jobs_result(2))

    async def scenario():
        service = _service(scraper)
        scrape_summary = service.start_scrape(("django",), ("upwork",), notify_discord=False)
        scraper.release.set()
        await service.wait_for_current_task()
        return service.read_scrape_report(scrape_summary.id).summary

    scrape_summary = asyncio.run(scenario())

    assert scrape_summary.discord_status is None
    assert scraper.sent_messages == []


def test_notify_sends_all_jobs_to_default_channel_with_mention():
    scraper = FakeScraper(_jobs_result(2))
    scraper.send_outcomes = [_file_delivery(2)]

    scrape_summary = _notified_scrape(scraper)

    assert scraper.sent_messages == [(CHANNEL_ID, True, None, [_job_view(0), _job_view(1)])]
    assert scrape_summary.status is ScrapeStatus.SUCCEEDED
    assert scrape_summary.discord_status is DiscordStatus.SENT
    assert (
        scrape_summary.discord_sent,
        scrape_summary.discord_failed,
        scrape_summary.discord_error,
    ) == (2, 0, None)


def test_notify_passes_the_scrape_keyword_site_and_error_counts():
    scraper = FakeScraper({**_jobs_result(2), "ok": False, "errors": [{"site": "x"}]})

    async def scenario():
        service = _service(scraper)
        service.start_scrape(("django", "flask", "go"), ("upwork", "glints"), notify_discord=True)
        scraper.release.set()
        await service.wait_for_current_task()

    asyncio.run(scenario())

    assert scraper.sent_digest_counts == [{"keyword_count": 3, "site_count": 2, "error_count": 1}]


def test_notify_without_mention_user_sends_without_mention():
    scraper = FakeScraper(_jobs_result(1))
    scraper.settings = {**DISCORD_SETTINGS, "mention_user_id": None}

    _notified_scrape(scraper)

    assert scraper.sent_messages[0][1] is False


def test_notify_sends_every_job_in_one_call_even_past_fifty():
    scraper = FakeScraper(_jobs_result(120))

    scrape_summary = _notified_scrape(scraper)

    assert [len(message[3]) for message in scraper.sent_messages] == [120]
    assert [message[1] for message in scraper.sent_messages] == [True]
    assert (scrape_summary.discord_sent, scrape_summary.discord_failed) == (120, 0)
    assert scrape_summary.discord_status is DiscordStatus.SENT


def test_notify_with_a_failed_file_counts_every_job_as_failed():
    scraper = FakeScraper(_jobs_result(3))
    scraper.send_outcomes = [_file_delivery(3, status="failed")]

    scrape_summary = _notified_scrape(scraper)

    assert scrape_summary.discord_status is DiscordStatus.FAILED
    assert (scrape_summary.discord_sent, scrape_summary.discord_failed) == (0, 3)


def test_notify_with_failed_text_message_is_failed():
    scraper = FakeScraper(_jobs_result(0))
    scraper.send_outcomes = [_text_delivery("failed")]

    scrape_summary = _notified_scrape(scraper)

    assert (scrape_summary.discord_sent, scrape_summary.discord_failed) == (0, 1)
    assert scrape_summary.discord_status is DiscordStatus.FAILED


def test_notify_with_the_send_raising_is_failed():
    scraper = FakeScraper(_jobs_result(120))
    scraper.send_outcomes = [DiscordUnauthorizedError()]

    scrape_summary = _notified_scrape(scraper)

    assert len(scraper.sent_messages) == 1
    assert scrape_summary.discord_status is DiscordStatus.FAILED
    assert (scrape_summary.discord_sent, scrape_summary.discord_failed) == (0, 0)
    assert scrape_summary.discord_error == DiscordUnauthorizedError.default_message


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

    scrape_summary = _notified_scrape(scraper)

    assert scrape_summary.discord_error == str(error)


def test_notify_text_with_long_keywords_fits_with_mention_prefix():
    async def scenario() -> list[tuple]:
        scraper = FakeScraper(McpUnavailableError("MCP down"))
        service = _service(scraper)
        service.start_scrape(("k" * 3000,), ("upwork",), notify_discord=True)
        scraper.release.set()
        await service.wait_for_current_task()
        return scraper.sent_messages

    text = asyncio.run(scenario())[0][2]

    assert len(f"<@{USER_ID}>\n{text}") <= 2000
    assert text.endswith(": MCP down")


def test_notify_text_without_overflow_is_unchanged():
    scraper = FakeScraper(McpUnavailableError("MCP down"))

    _notified_scrape(scraper)

    assert scraper.sent_messages[0][2] == "Run failed for django on upwork: MCP down"


def test_notify_with_zero_jobs_sends_one_text_message():
    scraper = FakeScraper(_jobs_result(0))

    scrape_summary = _notified_scrape(scraper)

    assert scraper.sent_messages == [(CHANNEL_ID, True, "django on upwork found 0 jobs", None)]
    assert scrape_summary.discord_status is DiscordStatus.SENT


def test_notify_after_failed_scrape_sends_failure_text():
    scraper = FakeScraper(McpUnavailableError("MCP down"))

    scrape_summary = _notified_scrape(scraper)

    assert scraper.sent_messages == [
        (CHANNEL_ID, True, "Run failed for django on upwork: MCP down", None)
    ]
    assert scrape_summary.status is ScrapeStatus.FAILED
    assert scrape_summary.discord_status is DiscordStatus.SENT


def test_notify_after_unexpected_failure_hides_detail_in_text():
    scraper = FakeScraper(RuntimeError("secret detail"))

    _notified_scrape(scraper)

    assert scraper.sent_messages[0][2] == "Run failed for django on upwork: The scrape failed."


def test_notify_without_token_fails_and_sends_nothing():
    scraper = FakeScraper(_jobs_result(1))
    scraper.settings = {**DISCORD_SETTINGS, "configured": False}

    scrape_summary = _notified_scrape(scraper)

    assert scraper.sent_messages == []
    assert scrape_summary.discord_status is DiscordStatus.FAILED
    assert scrape_summary.discord_error == "Discord token is not configured."
    assert scrape_summary.status is ScrapeStatus.SUCCEEDED


def test_notify_without_default_channel_fails_and_sends_nothing():
    scraper = FakeScraper(_jobs_result(1))
    scraper.settings = {**DISCORD_SETTINGS, "default_channel_id": None}

    scrape_summary = _notified_scrape(scraper)

    assert scraper.sent_messages == []
    assert scrape_summary.discord_status is DiscordStatus.FAILED
    assert scrape_summary.discord_error == "No default Discord channel is set."


def test_notify_send_error_hides_the_error_text():
    scraper = FakeScraper(_jobs_result(1))
    scraper.send_outcomes = [RuntimeError("secret detail")]

    scrape_summary = _notified_scrape(scraper)

    assert scrape_summary.discord_status is DiscordStatus.FAILED
    assert scrape_summary.discord_error == "Sending to Discord failed."
    assert scrape_summary.status is ScrapeStatus.SUCCEEDED


def test_notify_settings_error_marks_discord_failed():
    scraper = FakeScraper(_jobs_result(1))
    scraper.settings = McpUnavailableError("MCP down")

    scrape_summary = _notified_scrape(scraper)

    assert scrape_summary.discord_status is DiscordStatus.FAILED
    assert scrape_summary.discord_error == "Sending to Discord failed."


def test_scrape_stays_busy_while_discord_is_sending(monkeypatch: pytest.MonkeyPatch):
    async def scenario() -> tuple[DiscordStatus | None, bool]:
        scraper = FakeScraper(_jobs_result(1))
        gate = asyncio.Event()
        original = scraper.send_discord_message

        async def slow_send(*arguments, **options):
            await gate.wait()
            return await original(*arguments, **options)

        monkeypatch.setattr(scraper, "send_discord_message", slow_send)
        service = _service(scraper)
        scrape_summary = service.start_scrape(("django",), ("upwork",), notify_discord=True)
        scraper.release.set()
        for _ in range(20):
            await asyncio.sleep(0)
        current = service.read_scrape_report(scrape_summary.id).summary
        is_busy = False
        try:
            service.ensure_idle()
        except ScrapeInProgressError:
            is_busy = True
        gate.set()
        await service.wait_for_current_task()
        return current.discord_status, is_busy

    assert asyncio.run(scenario()) == (DiscordStatus.SENDING, True)


FAILED_PAYLOAD = {"error": "timeout", "keyword": "django", "jobs": [{"title": "never sent"}]}


def _payload_result() -> dict:
    return {
        "ok": False,
        "results": [
            *_jobs_result(1)["results"],
            {"keyword": "django", "site": "glints", "payload": FAILED_PAYLOAD},
        ],
        "errors": [{"keyword": "django", "site": "glints", "reason": "timeout"}],
        "raw_results": [{"keyword": "django", "site": "upwork", "payload": {"jobs": [1]}}],
    }


def _finished(scraper: FakeScraper, database: Any, notify_discord: bool = False):
    async def scenario():
        service = _service(scraper, database)
        scrape_summary = service.start_scrape(
            ("django",), ("upwork",), notify_discord=notify_discord
        )
        scraper.release.set()
        await service.wait_for_current_task()
        return service, scrape_summary

    return asyncio.run(scenario())


def test_running_detail_has_empty_lists():
    async def scenario():
        scraper = FakeScraper(_jobs_result(1))
        service = _service(scraper)
        scrape_summary = service.start_scrape(("django",), ("upwork",), notify_discord=False)
        scrape_report = service.read_scrape_report(scrape_summary.id)
        scraper.release.set()
        await service.wait_for_current_task()
        return scrape_report

    scrape_report = asyncio.run(scenario())

    assert scrape_report.summary.status is ScrapeStatus.RUNNING
    assert (scrape_report.jobs, scrape_report.failures, scrape_report.payloads) == ((), (), ())


def test_finished_scrape_detail_has_jobs_failures_and_payloads():
    service, scrape_summary = _finished(FakeScraper(_payload_result()), _database())

    scrape_report = service.read_scrape_report(scrape_summary.id)

    assert scrape_report.jobs == (_job_view(0),)
    assert scrape_report.summary.job_count == 1
    assert scrape_report.failures == ({"keyword": "django", "site": "glints", "reason": "timeout"},)
    assert scrape_report.payloads == (
        {"keyword": "django", "site": "upwork", "filtered": {"jobs": [{"title": "job 0"}]}},
        {"keyword": "django", "site": "glints", "filtered": FAILED_PAYLOAD},
    )


def test_finished_scrape_is_saved_to_ui_runs():
    database = _database()

    service, scrape_summary = _finished(FakeScraper(_payload_result()), database)

    document = database[SCRAPE_REPORTS_COLLECTION].find_one({"_id": scrape_summary.id})
    assert document["record"]["status"] == "partial"
    assert document["jobs"][0]["title"] == "job 0"
    assert document["failures"] == [{"keyword": "django", "site": "glints", "reason": "timeout"}]
    assert document["payloads"] == [
        {"keyword": "django", "site": "upwork", "filtered": {"jobs": [{"title": "job 0"}]}},
        {"keyword": "django", "site": "glints", "filtered": FAILED_PAYLOAD},
    ]


def test_failed_scrape_is_saved_with_empty_lists():
    database = _database()

    _, scrape_summary = _finished(FakeScraper(McpUnavailableError("MCP down")), database)

    document = database[SCRAPE_REPORTS_COLLECTION].find_one({"_id": scrape_summary.id})
    assert document["record"]["status"] == "failed"
    assert document["record"]["error"] == "MCP down"
    assert (document["jobs"], document["failures"], document["payloads"]) == ([], [], [])


def test_mcp_scrape_history_collection_is_never_written():
    database = _database()

    _finished(FakeScraper(_payload_result()), database)

    assert "scrape_runs" not in database.list_collection_names()


def test_only_the_latest_scrape_stays_in_ui_runs():
    async def scenario(database: Any) -> tuple[str, str]:
        scraper = FakeScraper(_jobs_result(1))
        service = _service(scraper, database)
        scraper.release.set()
        first = service.start_scrape(("django",), ("upwork",), notify_discord=False)
        await service.wait_for_current_task()
        second = service.start_scrape(("flask",), ("upwork",), notify_discord=False)
        await service.wait_for_current_task()
        return first.id, second.id

    database = _database()
    _, second_id = asyncio.run(scenario(database))

    ids = [document["_id"] for document in database[SCRAPE_REPORTS_COLLECTION].find()]
    assert ids == [second_id]


def test_discord_status_is_saved_to_the_stored_record():
    database = _database()
    scraper = FakeScraper(_jobs_result(2))
    scraper.send_outcomes = [_file_delivery(2)]

    _, scrape_summary = _finished(scraper, database, notify_discord=True)

    stored = database[SCRAPE_REPORTS_COLLECTION].find_one({"_id": scrape_summary.id})["record"]
    assert stored["discord_status"] == "sent"
    assert (stored["discord_sent"], stored["discord_failed"]) == (2, 0)
    assert stored["status"] == "succeeded"


def test_discord_failure_is_saved_to_the_stored_record():
    database = _database()
    scraper = FakeScraper(_jobs_result(1))
    scraper.settings = {**DISCORD_SETTINGS, "configured": False}

    _, scrape_summary = _finished(scraper, database, notify_discord=True)

    stored = database[SCRAPE_REPORTS_COLLECTION].find_one({"_id": scrape_summary.id})["record"]
    assert stored["discord_status"] == "failed"
    assert stored["discord_error"] == "Discord token is not configured."


def test_new_service_reads_the_stored_scrape():
    database = _database()
    _, scrape_summary = _finished(FakeScraper(_payload_result()), database)

    fresh = _service(FakeScraper({"ok": True}), database)

    assert _read_latest_report(fresh).summary.id == scrape_summary.id
    assert fresh.read_scrape_report(scrape_summary.id).jobs[0]["title"] == "job 0"


def test_latest_without_any_scrape_is_none():
    assert _service(FakeScraper({"ok": True})).read_latest_scrape_report() is None


def test_latest_prefers_the_current_scrape_over_the_stored_one():
    async def scenario(database: Any, old_id: str):
        scraper = FakeScraper(_jobs_result(1))
        service = _service(scraper, database)
        scrape_summary = service.start_scrape(("flask",), ("upwork",), notify_discord=False)
        latest = service.read_latest_scrape_report()
        stored = service.read_scrape_report(old_id)
        scraper.release.set()
        await service.wait_for_current_task()
        return scrape_summary, latest, stored

    database = _database()
    _, old = _finished(FakeScraper(_jobs_result(1)), database)
    scrape_summary, latest, stored = asyncio.run(scenario(database, old.id))

    assert latest.summary.id == scrape_summary.id
    assert latest.summary.status is ScrapeStatus.RUNNING
    assert stored.summary.id == old.id


def test_scrape_works_from_memory_when_mongo_is_down(caplog: pytest.LogCaptureFixture):
    client: Any = MongoClient("mongodb://127.0.0.1:1", serverSelectionTimeoutMS=50)
    scraper = FakeScraper(_payload_result())
    scraper.send_outcomes = [_file_delivery(1)]

    with caplog.at_level(logging.WARNING, logger="scraper-ui"):
        service, scrape_summary = _finished(scraper, client["job_scraper"], notify_discord=True)

    scrape_report = service.read_scrape_report(scrape_summary.id)
    assert scrape_report.summary.status is ScrapeStatus.PARTIAL
    assert scrape_report.summary.discord_status is DiscordStatus.SENT
    assert scrape_report.jobs[0]["title"] == "job 0"
    assert service.read_latest_scrape_report() == scrape_report
    assert "ui_runs" in caplog.text
    with pytest.raises(ScrapeStorageUnavailableError):
        service.read_scrape_report("20261101T010000Z-abc123")


def test_storage_unavailable_error_is_503_with_a_clear_message():
    error = ScrapeStorageUnavailableError()

    assert error.status_code == 503
    assert error.message == "Run storage is unavailable."


def test_latest_is_none_when_mongo_is_down_and_nothing_is_in_memory():
    client: Any = MongoClient("mongodb://127.0.0.1:1", serverSelectionTimeoutMS=50)

    assert (
        _service(FakeScraper({"ok": True}), client["job_scraper"]).read_latest_scrape_report()
        is None
    )


@pytest.mark.parametrize(
    "result",
    [
        {"ok": True, "results": [None], "errors": []},
        {"ok": True, "results": "garbage", "errors": []},
        {"ok": True, "results": [{"keyword": "django", "site": "upwork"}], "errors": []},
        {
            "ok": True,
            "results": [{"keyword": "django", "site": "upwork", "payload": {"jobs": 5}}],
            "errors": [],
        },
        {
            "ok": True,
            "results": [{"keyword": "django", "site": "upwork", "payload": "not a dict"}],
            "errors": [],
        },
        {"ok": True, "results": [{"keyword": "django", "sites": [{"jobs": []}]}], "errors": []},
        {"ok": True, "results": [], "errors": 7},
    ],
)
def test_malformed_result_fails_the_scrape_with_the_generic_message(result: dict):
    async def scenario(database: Any):
        scraper = FakeScraper(result)
        service = _service(scraper, database)
        scrape_summary = service.start_scrape(("django",), ("upwork",), notify_discord=False)
        scraper.release.set()
        await service.wait_for_current_task()
        service.ensure_idle()
        return service.read_scrape_report(scrape_summary.id).summary

    database = _database()
    scrape_summary = asyncio.run(scenario(database))

    assert scrape_summary.status is ScrapeStatus.FAILED
    assert scrape_summary.error == "The scrape failed."
    assert scrape_summary.finished_at is not None
    stored = database[SCRAPE_REPORTS_COLLECTION].find_one({"_id": scrape_summary.id})
    assert stored["record"]["status"] == "failed"


def test_malformed_result_still_reports_the_failure_to_discord():
    scraper = FakeScraper({"ok": True, "results": [None], "errors": []})

    scrape_summary = _notified_scrape(scraper)

    assert scrape_summary.status is ScrapeStatus.FAILED
    assert scrape_summary.discord_status is DiscordStatus.SENT
    assert "The scrape failed." in scraper.sent_messages[0][2]


class _BrokenSaveRepository(MongoScrapeReportRepository):
    def save(self, scrape_report: Any) -> None:
        raise RuntimeError("boom")


def test_scrape_ends_with_a_terminal_status_when_saving_crashes():
    async def scenario():
        scraper = FakeScraper(_jobs_result(1))
        service = ScrapeService(scraper, _BrokenSaveRepository(_database()))
        service.start_scrape(("django",), ("upwork",), notify_discord=False)
        scraper.release.set()
        await service.wait_for_current_task()
        service.ensure_idle()
        return service.read_latest_scrape_report()

    scrape_report = asyncio.run(scenario())

    assert scrape_report.summary.status is not ScrapeStatus.RUNNING


def _resent(scraper: FakeScraper, database: Any = None):
    async def scenario():
        service = _service(scraper, database)
        service.start_scrape(("django",), ("upwork",), notify_discord=False)
        scraper.release.set()
        await service.wait_for_current_task()
        sending = await service.send_latest_scrape_to_discord()
        await service.wait_for_current_task()
        return service, sending

    return asyncio.run(scenario())


def _resent_after_restart(scraper: FakeScraper, database: Any):
    async def scenario():
        fresh = _service(scraper, database)
        sending = await fresh.send_latest_scrape_to_discord()
        await fresh.wait_for_current_task()
        return fresh, sending

    return asyncio.run(scenario())


def test_send_latest_answers_with_the_sending_record_before_anything_is_sent():
    async def scenario():
        scraper = FakeScraper(_jobs_result(2))
        service = _service(scraper)
        scrape_summary = service.start_scrape(("django",), ("upwork",), notify_discord=False)
        scraper.release.set()
        await service.wait_for_current_task()
        sending = await service.send_latest_scrape_to_discord()
        shown = service.read_latest_scrape_report()
        sent_so_far = list(scraper.sent_messages)
        await service.wait_for_current_task()
        return scrape_summary, sending, shown, sent_so_far

    scrape_summary, sending, shown, sent_so_far = asyncio.run(scenario())

    assert sending.id == scrape_summary.id
    assert sending.status is ScrapeStatus.SUCCEEDED
    assert sending.discord_status is DiscordStatus.SENDING
    assert shown.summary == sending
    assert shown.jobs == (_job_view(0), _job_view(1))
    assert sent_so_far == []


def test_send_latest_sends_the_jobs_like_a_notified_scrape():
    database = _database()
    scraper = FakeScraper(_jobs_result(2))
    scraper.send_outcomes = [_file_delivery(2)]

    service, sending = _resent(scraper, database)

    scrape_report = service.read_latest_scrape_report()
    assert scraper.sent_messages == [(CHANNEL_ID, True, None, [_job_view(0), _job_view(1)])]
    assert scrape_report.summary.discord_status is DiscordStatus.SENT
    assert (scrape_report.summary.discord_sent, scrape_report.summary.discord_failed) == (2, 0)
    assert scrape_report.summary.discord_error is None
    assert scrape_report.jobs == (_job_view(0), _job_view(1))
    stored = database[SCRAPE_REPORTS_COLLECTION].find_one({"_id": sending.id})
    assert stored["record"]["discord_status"] == "sent"
    assert stored["record"]["discord_sent"] == 2
    assert [job["title"] for job in stored["jobs"]] == ["job 0", "job 1"]


def test_send_latest_can_send_the_same_scrape_again():
    async def scenario():
        scraper = FakeScraper(_jobs_result(1))
        service = _service(scraper)
        service.start_scrape(("django",), ("upwork",), notify_discord=True)
        scraper.release.set()
        await service.wait_for_current_task()
        await service.send_latest_scrape_to_discord()
        await service.wait_for_current_task()
        return scraper, _read_latest_report(service).summary

    scraper, scrape_summary = asyncio.run(scenario())

    assert len(scraper.sent_messages) == 2
    assert scrape_summary.discord_status is DiscordStatus.SENT
    assert scrape_summary.discord_sent == 1


def test_send_latest_passes_the_stored_scrape_counts():
    scraper = FakeScraper(_payload_result())

    _resent(scraper)

    assert scraper.sent_digest_counts == [{"keyword_count": 1, "site_count": 1, "error_count": 1}]


def test_zero_jobs_text_send_passes_no_digest_counts():
    scraper = FakeScraper(_jobs_result(0))

    _notified_scrape(scraper)

    assert scraper.sent_digest_counts == [None]


def test_send_latest_sends_a_partial_scrape():
    scraper = FakeScraper(_payload_result())

    service, _ = _resent(scraper)

    scrape_summary = service.read_latest_scrape_report().summary
    assert scrape_summary.status is ScrapeStatus.PARTIAL
    assert scrape_summary.discord_status is DiscordStatus.SENT
    assert scraper.sent_messages == [(CHANNEL_ID, True, None, [_job_view(0)])]


def test_send_latest_with_zero_jobs_sends_the_empty_scrape_text():
    scraper = FakeScraper(_jobs_result(0))

    service, _ = _resent(scraper)

    scrape_summary = service.read_latest_scrape_report().summary
    assert scraper.sent_messages == [(CHANNEL_ID, True, "django on upwork found 0 jobs", None)]
    assert scrape_summary.discord_status is DiscordStatus.SENT
    assert (scrape_summary.discord_sent, scrape_summary.discord_failed) == (1, 0)


def test_send_latest_without_token_fails_and_sends_nothing():
    scraper = FakeScraper(_jobs_result(1))
    scraper.settings = {**DISCORD_SETTINGS, "configured": False}

    service, _ = _resent(scraper)

    scrape_report = service.read_latest_scrape_report()
    assert scraper.sent_messages == []
    assert scrape_report.summary.discord_status is DiscordStatus.FAILED
    assert scrape_report.summary.discord_error == "Discord token is not configured."
    assert scrape_report.jobs == (_job_view(0),)


def test_send_latest_without_default_channel_fails_and_sends_nothing():
    scraper = FakeScraper(_jobs_result(1))
    scraper.settings = {**DISCORD_SETTINGS, "default_channel_id": None}

    service, _ = _resent(scraper)

    scrape_summary = service.read_latest_scrape_report().summary
    assert scraper.sent_messages == []
    assert scrape_summary.discord_status is DiscordStatus.FAILED
    assert scrape_summary.discord_error == "No default Discord channel is set."


def test_send_latest_keeps_the_error_of_a_failed_send():
    scraper = FakeScraper(_jobs_result(1))
    scraper.send_outcomes = [DiscordForbiddenError()]

    service, _ = _resent(scraper)

    scrape_summary = service.read_latest_scrape_report().summary
    assert scrape_summary.discord_status is DiscordStatus.FAILED
    assert scrape_summary.discord_error == DiscordForbiddenError.default_message
    assert scrape_summary.status is ScrapeStatus.SUCCEEDED


def test_send_latest_without_any_scrape_is_refused():
    async def scenario() -> None:
        scraper = FakeScraper({"ok": True})
        service = _service(scraper)
        with pytest.raises(ScrapeNotFoundError) as refusal:
            await service.send_latest_scrape_to_discord()
        assert refusal.value.message == "There is no run to send yet."
        service.ensure_idle()
        assert scraper.sent_messages == []

    asyncio.run(scenario())


def test_send_latest_is_refused_while_a_scrape_is_in_progress():
    async def scenario() -> None:
        scraper = FakeScraper(_jobs_result(1))
        service = _service(scraper)
        service.start_scrape(("django",), ("upwork",), notify_discord=False)
        with pytest.raises(ScrapeInProgressError):
            await service.send_latest_scrape_to_discord()
        scraper.release.set()
        await service.wait_for_current_task()
        assert scraper.sent_messages == []

    asyncio.run(scenario())


def test_send_latest_of_a_failed_scrape_is_refused():
    async def scenario() -> None:
        scraper = FakeScraper(McpUnavailableError("MCP down"))
        service = _service(scraper)
        service.start_scrape(("django",), ("upwork",), notify_discord=False)
        scraper.release.set()
        await service.wait_for_current_task()
        with pytest.raises(ScrapeNotSendableError):
            await service.send_latest_scrape_to_discord()
        service.ensure_idle()
        assert _read_latest_report(service).summary.discord_status is None
        assert scraper.sent_messages == []

    asyncio.run(scenario())


def test_send_latest_of_a_stored_scrape_that_never_finished_is_refused():
    database = _database()
    database[SCRAPE_REPORTS_COLLECTION].insert_one(
        {
            "_id": "20261118T010000Z-abcdef",
            "saved_at": "2026-11-18T01:01:00+00:00",
            "record": {
                "id": "20261118T010000Z-abcdef",
                "status": "running",
                "keywords": ["django"],
                "sites": ["upwork"],
                "started_at": "2026-11-18T01:00:00+00:00",
            },
            "jobs": [],
            "failures": [],
            "payloads": [],
        }
    )

    async def scenario() -> None:
        service = _service(FakeScraper({"ok": True}), database)
        with pytest.raises(ScrapeNotSendableError):
            await service.send_latest_scrape_to_discord()

    asyncio.run(scenario())


def test_scrape_not_sendable_error_is_409_with_a_clear_message():
    error = ScrapeNotSendableError()

    assert error.status_code == 409
    assert error.message == "Only a finished run can be sent to Discord."


def test_second_send_latest_is_refused_while_the_first_is_sending(
    monkeypatch: pytest.MonkeyPatch,
):
    async def scenario():
        scraper = FakeScraper(_jobs_result(1))
        gate = asyncio.Event()
        original = scraper.send_discord_message

        async def slow_send(*arguments, **options):
            await gate.wait()
            return await original(*arguments, **options)

        monkeypatch.setattr(scraper, "send_discord_message", slow_send)
        service = _service(scraper)
        service.start_scrape(("django",), ("upwork",), notify_discord=False)
        scraper.release.set()
        await service.wait_for_current_task()
        await service.send_latest_scrape_to_discord()
        for _ in range(20):
            await asyncio.sleep(0)
        with pytest.raises(ScrapeInProgressError):
            await service.send_latest_scrape_to_discord()
        with pytest.raises(ScrapeInProgressError):
            service.start_scrape(("flask",), ("upwork",), notify_discord=False)
        gate.set()
        await service.wait_for_current_task()
        return scraper, _read_latest_report(service).summary

    scraper, scrape_summary = asyncio.run(scenario())

    assert len(scraper.sent_messages) == 1
    assert scrape_summary.discord_status is DiscordStatus.SENT


def test_a_new_scrape_can_start_after_send_latest_settles():
    async def scenario():
        scraper = FakeScraper(_jobs_result(1))
        service = _service(scraper)
        service.start_scrape(("django",), ("upwork",), notify_discord=False)
        scraper.release.set()
        await service.wait_for_current_task()
        await service.send_latest_scrape_to_discord()
        await service.wait_for_current_task()
        second = service.start_scrape(("flask",), ("upwork",), notify_discord=False)
        await service.wait_for_current_task()
        return second, _read_latest_report(service).summary

    second, scrape_summary = asyncio.run(scenario())

    assert scrape_summary.id == second.id
    assert scrape_summary.discord_status is None


def test_send_latest_after_a_restart_keeps_the_stored_jobs_failures_and_payloads():
    database = _database()
    _, old = _finished(FakeScraper(_payload_result()), database)
    scraper = FakeScraper({"ok": True})

    fresh, sending = _resent_after_restart(scraper, database)

    scrape_report = fresh.read_latest_scrape_report()
    assert sending.id == old.id
    assert scraper.sent_messages == [(CHANNEL_ID, True, None, [_job_view(0)])]
    assert scrape_report.summary.discord_status is DiscordStatus.SENT
    assert scrape_report.summary.discord_sent == 1
    assert scrape_report.jobs == (_job_view(0),)
    assert scrape_report.failures == ({"keyword": "django", "site": "glints", "reason": "timeout"},)
    assert len(scrape_report.payloads) == 2
    assert fresh.read_scrape_report(old.id) == scrape_report
    stored = database[SCRAPE_REPORTS_COLLECTION].find_one({"_id": old.id})
    assert stored["record"]["discord_status"] == "sent"
    assert stored["jobs"][0]["title"] == "job 0"
    assert len(stored["payloads"]) == 2


def test_send_latest_after_a_restart_keeps_the_jobs_when_discord_is_not_set_up():
    database = _database()
    _, old = _finished(FakeScraper(_jobs_result(2)), database)
    scraper = FakeScraper({"ok": True})
    scraper.settings = {**DISCORD_SETTINGS, "configured": False}

    fresh, _ = _resent_after_restart(scraper, database)

    scrape_report = fresh.read_latest_scrape_report()
    assert scrape_report.summary.id == old.id
    assert scrape_report.summary.discord_status is DiscordStatus.FAILED
    assert scrape_report.jobs == (_job_view(0), _job_view(1))


class _BrokenSummarySaveRepository(MongoScrapeReportRepository):
    def save_summary(self, scrape_summary: Any) -> None:
        raise RuntimeError("boom")


def test_send_latest_ends_as_failed_when_saving_the_status_crashes():
    async def scenario():
        scraper = FakeScraper(_jobs_result(1))
        service = ScrapeService(scraper, _BrokenSummarySaveRepository(_database()))
        service.start_scrape(("django",), ("upwork",), notify_discord=False)
        scraper.release.set()
        await service.wait_for_current_task()
        await service.send_latest_scrape_to_discord()
        await service.wait_for_current_task()
        service.ensure_idle()
        return service.read_latest_scrape_report()

    scrape_report = asyncio.run(scenario())

    assert scrape_report.summary.discord_status is DiscordStatus.FAILED
    assert scrape_report.summary.discord_error == "Sending to Discord failed."
    assert scrape_report.jobs == (_job_view(0),)
