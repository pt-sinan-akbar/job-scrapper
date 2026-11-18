from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from typing import Any, Protocol

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
from ui_server.schema.discord import MAX_JOBS, MAX_TEXT_CHARS
from ui_server.services.run_detail import RunDetail, build_detail
from ui_server.services.run_record import (
    DiscordStatus,
    RunRecord,
    RunStatus,
    fail_run,
    finish_run,
    flatten_jobs,
    new_run,
    with_discord,
)
from ui_server.services.run_repository import RunRepository, RunStoreUnavailableError

LOG = logging.getLogger("scraper-ui")
RUN_FAILED_MESSAGE = "The scrape failed."
DISCORD_NO_TOKEN_MESSAGE = "Discord token is not configured."
DISCORD_NO_CHANNEL_MESSAGE = "No default Discord channel is set."
DISCORD_SEND_FAILED_MESSAGE = "Sending to Discord failed."
DISCORD_MENTION_RESERVE = 24
DISCORD_KNOWN_ERRORS = (
    DiscordNotConfiguredError,
    DiscordUnauthorizedError,
    DiscordForbiddenError,
    ConfigInvalidError,
    McpUnavailableError,
)


class Scraper(Protocol):
    async def scrape_jobs(
        self, sites: tuple[str, ...], keywords: tuple[str, ...]
    ) -> dict[str, Any]: ...

    async def read_discord_settings(self) -> dict[str, Any]: ...

    async def send_discord_message(
        self, channel_id: str, mention: bool, text: str | None, jobs: list[dict[str, Any]] | None
    ) -> dict[str, Any]: ...


def _fit_text(lead: str, tail: str = "") -> str:
    limit = MAX_TEXT_CHARS - DISCORD_MENTION_RESERVE
    kept_tail = tail[:limit]
    return lead[: limit - len(kept_tail)] + kept_tail


def _discord_text(record: RunRecord) -> str:
    keywords = ", ".join(record.keywords)
    sites = ", ".join(record.sites)
    if record.error:
        return _fit_text(f"Run failed for {keywords} on {sites}", f": {record.error}")
    return _fit_text(f"{keywords} on {sites} found 0 jobs")


def _count_kind(result: dict[str, Any], kind: str) -> tuple[int, int]:
    entries = [entry for entry in result["results"] if entry["kind"] == kind]
    failed = sum(1 for entry in entries if entry["status"] == "failed")
    return len(entries) - failed, failed


def _send_error_message(run_id: str, exc: Exception) -> str:
    if isinstance(exc, DISCORD_KNOWN_ERRORS):
        return exc.message
    LOG.error("run %s discord send failed", run_id, exc_info=exc)
    return DISCORD_SEND_FAILED_MESSAGE


def _discord_status(sent: int, failed: int) -> DiscordStatus:
    if sent == 0:
        return DiscordStatus.FAILED
    return DiscordStatus.PARTIAL if failed > 0 else DiscordStatus.SENT


def _batches(
    record: RunRecord, jobs: list[dict[str, Any]]
) -> list[tuple[str | None, list[dict[str, Any]] | None]]:
    if not jobs:
        return [(_discord_text(record), None)]
    return [(None, jobs[start : start + MAX_JOBS]) for start in range(0, len(jobs), MAX_JOBS)]


Outcome = tuple[RunDetail, list[dict[str, Any]]]


def _failed(record: RunRecord, message: str) -> Outcome:
    return RunDetail(fail_run(record, message)), []


def _finished(record: RunRecord, result: dict[str, Any]) -> Outcome:
    try:
        return build_detail(finish_run(record, result), result), flatten_jobs(result)
    except Exception:
        LOG.exception("run %s returned a result that could not be read", record.id)
        return _failed(record, RUN_FAILED_MESSAGE)


class RunService:
    def __init__(self, scraper: Scraper, repository: RunRepository) -> None:
        self._scraper = scraper
        self._repository = repository
        self._task: asyncio.Task[None] | None = None
        self._detail: RunDetail | None = None

    def ensure_idle(self) -> None:
        if self._task is not None and not self._task.done():
            raise RunInProgressError()

    def get(self, run_id: str) -> RunDetail:
        if self._detail is not None and self._detail.record.id == run_id:
            return self._detail
        try:
            stored = self._repository.find(run_id)
        except RunStoreUnavailableError as exc:
            raise RunStorageUnavailableError() from exc
        if stored is None:
            raise RunNotFoundError()
        return stored

    def latest(self) -> RunDetail | None:
        return self._detail if self._detail is not None else self._repository.latest()

    def start(
        self, keywords: tuple[str, ...], sites: tuple[str, ...], notify_discord: bool
    ) -> RunRecord:
        self.ensure_idle()
        record = new_run(keywords, sites)
        self._detail = RunDetail(record)
        self._task = asyncio.create_task(self._execute(record, notify_discord))
        return record

    async def wait(self) -> None:
        if self._task is not None:
            await self._task

    async def _keep(self, record: RunRecord) -> RunRecord:
        self._detail = replace(self._detail or RunDetail(record), record=record)
        if record.status is not RunStatus.RUNNING:
            await asyncio.to_thread(self._repository.save_record, record)
        return record

    async def _save(self, detail: RunDetail) -> None:
        self._detail = detail
        await asyncio.to_thread(self._repository.save, detail)

    async def _scrape(self, record: RunRecord) -> Outcome:
        try:
            result = await self._scraper.scrape_jobs(record.sites, record.keywords)
        except McpUnavailableError as exc:
            return _failed(record, exc.message)
        except Exception:
            LOG.exception("run %s failed", record.id)
            return _failed(record, RUN_FAILED_MESSAGE)
        return _finished(record, result)

    async def _execute(self, record: RunRecord, notify_discord: bool) -> None:
        try:
            await self._complete(record, notify_discord)
        except Exception:
            LOG.exception("run %s crashed", record.id)
            self._end_running(record)

    async def _complete(self, record: RunRecord, notify_discord: bool) -> None:
        detail, jobs = await self._scrape(record)
        await self._save(detail)
        if notify_discord:
            await self._notify_discord(detail.record, jobs)

    def _end_running(self, record: RunRecord) -> None:
        current = self._detail or RunDetail(record)
        if current.record.status is RunStatus.RUNNING:
            self._detail = RunDetail(fail_run(current.record, RUN_FAILED_MESSAGE))

    async def _fail_discord(self, record: RunRecord, message: str) -> None:
        await self._keep(with_discord(record, DiscordStatus.FAILED, error=message))

    async def _notify_discord(self, record: RunRecord, jobs: list[dict[str, Any]]) -> None:
        sending = await self._keep(with_discord(record, DiscordStatus.SENDING))
        try:
            settings = await self._scraper.read_discord_settings()
            if not settings.get("configured"):
                await self._fail_discord(sending, DISCORD_NO_TOKEN_MESSAGE)
                return
            channel_id = settings.get("default_channel_id")
            if not channel_id:
                await self._fail_discord(sending, DISCORD_NO_CHANNEL_MESSAGE)
                return
            mention = bool(settings.get("mention_user_id"))
            await self._send(sending, channel_id, mention, jobs)
        except Exception:
            LOG.exception("run %s discord notify failed", record.id)
            await self._fail_discord(sending, DISCORD_SEND_FAILED_MESSAGE)

    async def _send(
        self, record: RunRecord, channel_id: str, mention: bool, jobs: list[dict[str, Any]]
    ) -> None:
        batches = _batches(record, jobs)
        kind = "job" if jobs else "text"
        sent = 0
        failed = 0
        for index, (text, chunk) in enumerate(batches):
            try:
                result = await self._scraper.send_discord_message(
                    channel_id, mention and index == 0, text, chunk
                )
            except Exception as exc:
                message = _send_error_message(record.id, exc)
                status = DiscordStatus.PARTIAL if sent > 0 else DiscordStatus.FAILED
                await self._keep(with_discord(record, status, sent, failed, message))
                return
            chunk_sent, chunk_failed = _count_kind(result, kind)
            sent += chunk_sent
            failed += chunk_failed
        await self._keep(with_discord(record, _discord_status(sent, failed), sent, failed))
