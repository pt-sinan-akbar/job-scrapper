from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from typing import Any, Protocol

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
from backend.schemas.discord import MAX_TEXT_CHARS
from backend.services.scrape_report import ScrapeReport, build_scrape_report
from backend.services.scrape_report_repository import (
    ScrapeReportRepository,
    ScrapeStoreUnavailableError,
)
from backend.services.scrape_summary import (
    DiscordStatus,
    ScrapeStatus,
    ScrapeSummary,
    build_failed_summary,
    build_finished_summary,
    build_running_summary,
    copy_summary_with_discord_status,
)

LOG = logging.getLogger("scraper-ui")
SCRAPE_FAILED_MESSAGE = "The scrape failed."
DISCORD_NO_TOKEN_MESSAGE = "Discord token is not configured."
DISCORD_NO_CHANNEL_MESSAGE = "No default Discord channel is set."
DISCORD_SEND_FAILED_MESSAGE = "Sending to Discord failed."
NO_SCRAPE_TO_SEND_MESSAGE = "There is no run to send yet."
SENDABLE_SCRAPE_STATUSES = frozenset({ScrapeStatus.SUCCEEDED, ScrapeStatus.PARTIAL})
DISCORD_MENTION_RESERVE = 24
DISCORD_KNOWN_ERRORS = (
    DiscordNotConfiguredError,
    DiscordUnauthorizedError,
    DiscordForbiddenError,
    ConfigInvalidError,
    McpUnavailableError,
)

ScrapeOutcome = tuple[ScrapeReport, list[dict[str, Any]]]


class Scraper(Protocol):
    async def scrape_jobs(
        self,
        sites: tuple[str, ...],
        keywords: tuple[str, ...],
        location: str | None = None,
        max_age_hours: int | None = None,
    ) -> dict[str, Any]: ...

    async def read_discord_settings(self) -> dict[str, Any]: ...

    async def send_discord_message(
        self,
        channel_id: str,
        mention: bool,
        text: str | None,
        jobs: list[dict[str, Any]] | None,
        digest_counts: dict[str, int] | None = None,
    ) -> dict[str, Any]: ...


class ScrapeService:
    def __init__(self, scraper: Scraper, repository: ScrapeReportRepository) -> None:
        self._scraper = scraper
        self._repository = repository
        self._task: asyncio.Task[None] | None = None
        self._latest_scrape_report: ScrapeReport | None = None

    def ensure_idle(self) -> None:
        if self._task is not None and not self._task.done():
            raise ScrapeInProgressError()

    def read_scrape_report(self, scrape_id: str) -> ScrapeReport:
        if self._latest_scrape_report is not None and self._is_latest_scrape(scrape_id):
            return self._latest_scrape_report
        try:
            stored_report = self._repository.find(scrape_id)
        except ScrapeStoreUnavailableError as exc:
            raise ScrapeStorageUnavailableError() from exc
        if stored_report is None:
            raise ScrapeNotFoundError()
        return stored_report

    def read_latest_scrape_report(self) -> ScrapeReport | None:
        if self._latest_scrape_report is not None:
            return self._latest_scrape_report
        return self._repository.find_latest()

    def start_scrape(
        self,
        keywords: tuple[str, ...],
        sites: tuple[str, ...],
        notify_discord: bool,
        location: str | None = None,
        max_age_hours: int | None = None,
    ) -> ScrapeSummary:
        self.ensure_idle()
        scrape_summary = build_running_summary(keywords, sites, location, max_age_hours)
        self._latest_scrape_report = ScrapeReport(scrape_summary)
        background_scrape = self._scrape_or_mark_failed(scrape_summary, notify_discord)
        self._task = asyncio.create_task(background_scrape)
        return scrape_summary

    async def send_latest_scrape_to_discord(self) -> ScrapeSummary:
        self.ensure_idle()
        if self._latest_scrape_report is not None:
            return self._start_sending_scrape_to_discord(self._latest_scrape_report)
        stored_report = await asyncio.to_thread(self._repository.find_latest)
        return self._start_sending_scrape_to_discord(stored_report)

    async def wait_for_current_task(self) -> None:
        if self._task is not None:
            await self._task

    def _is_latest_scrape(self, scrape_id: str) -> bool:
        if self._latest_scrape_report is None:
            return False
        return self._latest_scrape_report.summary.id == scrape_id

    async def _scrape_or_mark_failed(
        self, scrape_summary: ScrapeSummary, notify_discord: bool
    ) -> None:
        try:
            await self._scrape_save_and_notify_if_asked(scrape_summary, notify_discord)
        except Exception:
            LOG.exception("scrape %s crashed", scrape_summary.id)
            self._mark_unfinished_scrape_failed(scrape_summary)

    async def _scrape_save_and_notify_if_asked(
        self, scrape_summary: ScrapeSummary, notify_discord: bool
    ) -> None:
        scrape_report, jobs = await self._scrape_jobs_for_summary(scrape_summary)
        await self._save_report(scrape_report)
        if notify_discord:
            await self._send_scrape_to_discord(scrape_report.summary, jobs)

    async def _scrape_jobs_for_summary(self, scrape_summary: ScrapeSummary) -> ScrapeOutcome:
        try:
            scrape_response = await self._scraper.scrape_jobs(
                scrape_summary.sites,
                scrape_summary.keywords,
                scrape_summary.location,
                scrape_summary.max_age_hours,
            )
        except McpUnavailableError as exc:
            return _build_failed_outcome(scrape_summary, exc.message)
        except Exception:
            LOG.exception("scrape %s failed", scrape_summary.id)
            return _build_failed_outcome(scrape_summary, SCRAPE_FAILED_MESSAGE)
        return _build_finished_outcome(scrape_summary, scrape_response)

    def _mark_unfinished_scrape_failed(self, scrape_summary: ScrapeSummary) -> None:
        current_report = self._read_current_report(scrape_summary)
        if current_report.summary.status is not ScrapeStatus.RUNNING:
            return
        failed_summary = build_failed_summary(current_report.summary, SCRAPE_FAILED_MESSAGE)
        self._latest_scrape_report = ScrapeReport(failed_summary)

    def _start_sending_scrape_to_discord(self, scrape_report: ScrapeReport | None) -> ScrapeSummary:
        self.ensure_idle()
        if scrape_report is None:
            raise ScrapeNotFoundError(NO_SCRAPE_TO_SEND_MESSAGE)
        if scrape_report.summary.status not in SENDABLE_SCRAPE_STATUSES:
            raise ScrapeNotSendableError()
        sending_summary = copy_summary_with_discord_status(
            scrape_report.summary, DiscordStatus.SENDING
        )
        self._latest_scrape_report = replace(scrape_report, summary=sending_summary)
        background_send = self._send_to_discord_or_mark_failed(
            sending_summary, list(scrape_report.jobs)
        )
        self._task = asyncio.create_task(background_send)
        return sending_summary

    async def _send_to_discord_or_mark_failed(
        self, scrape_summary: ScrapeSummary, jobs: list[dict[str, Any]]
    ) -> None:
        try:
            await self._send_scrape_to_discord(scrape_summary, jobs)
        except Exception:
            LOG.exception("scrape %s discord send crashed", scrape_summary.id)
            self._mark_sending_discord_failed(scrape_summary)

    def _mark_sending_discord_failed(self, scrape_summary: ScrapeSummary) -> None:
        current_report = self._latest_scrape_report
        if current_report is None or current_report.summary.id != scrape_summary.id:
            return
        if current_report.summary.discord_status is not DiscordStatus.SENDING:
            return
        failed_summary = copy_summary_with_discord_status(
            current_report.summary, DiscordStatus.FAILED, error=DISCORD_SEND_FAILED_MESSAGE
        )
        self._latest_scrape_report = replace(current_report, summary=failed_summary)

    async def _send_scrape_to_discord(
        self, scrape_summary: ScrapeSummary, jobs: list[dict[str, Any]]
    ) -> None:
        sending_summary = await self._save_summary(
            copy_summary_with_discord_status(scrape_summary, DiscordStatus.SENDING)
        )
        try:
            discord_settings = await self._scraper.read_discord_settings()
            if not discord_settings.get("configured"):
                await self._mark_discord_failed(sending_summary, DISCORD_NO_TOKEN_MESSAGE)
                return
            channel_id = discord_settings.get("default_channel_id")
            if not channel_id:
                await self._mark_discord_failed(sending_summary, DISCORD_NO_CHANNEL_MESSAGE)
                return
            mention = bool(discord_settings.get("mention_user_id"))
            await self._send_jobs_and_save_counts(sending_summary, channel_id, mention, jobs)
        except Exception:
            LOG.exception("scrape %s discord notify failed", scrape_summary.id)
            await self._mark_discord_failed(sending_summary, DISCORD_SEND_FAILED_MESSAGE)

    async def _send_jobs_and_save_counts(
        self,
        scrape_summary: ScrapeSummary,
        channel_id: str,
        mention: bool,
        jobs: list[dict[str, Any]],
    ) -> None:
        try:
            discord_delivery = await self._post_scrape_to_discord(
                scrape_summary, channel_id, mention, jobs
            )
        except Exception as exc:
            message = _build_send_error_message(scrape_summary.id, exc)
            await self._mark_discord_failed(scrape_summary, message)
            return
        sent, failed = _count_delivered_jobs(discord_delivery)
        discord_status = _pick_discord_status(sent, failed)
        await self._save_summary(
            copy_summary_with_discord_status(scrape_summary, discord_status, sent, failed)
        )

    async def _post_scrape_to_discord(
        self,
        scrape_summary: ScrapeSummary,
        channel_id: str,
        mention: bool,
        jobs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not jobs:
            no_jobs_text = _build_no_jobs_text(scrape_summary)
            return await self._scraper.send_discord_message(channel_id, mention, no_jobs_text, None)
        digest_counts = _build_digest_counts(scrape_summary)
        return await self._scraper.send_discord_message(
            channel_id, mention, None, jobs, digest_counts=digest_counts
        )

    async def _mark_discord_failed(self, scrape_summary: ScrapeSummary, message: str) -> None:
        failed_summary = copy_summary_with_discord_status(
            scrape_summary, DiscordStatus.FAILED, error=message
        )
        await self._save_summary(failed_summary)

    async def _save_summary(self, scrape_summary: ScrapeSummary) -> ScrapeSummary:
        current_report = self._read_current_report(scrape_summary)
        self._latest_scrape_report = replace(current_report, summary=scrape_summary)
        if scrape_summary.status is not ScrapeStatus.RUNNING:
            await asyncio.to_thread(self._repository.save_summary, scrape_summary)
        return scrape_summary

    async def _save_report(self, scrape_report: ScrapeReport) -> None:
        self._latest_scrape_report = scrape_report
        await asyncio.to_thread(self._repository.save, scrape_report)

    def _read_current_report(self, scrape_summary: ScrapeSummary) -> ScrapeReport:
        if self._latest_scrape_report is not None:
            return self._latest_scrape_report
        return ScrapeReport(scrape_summary)


def _build_failed_outcome(scrape_summary: ScrapeSummary, message: str) -> ScrapeOutcome:
    failed_report = ScrapeReport(build_failed_summary(scrape_summary, message))
    return failed_report, []


def _build_finished_outcome(
    scrape_summary: ScrapeSummary, scrape_response: dict[str, Any]
) -> ScrapeOutcome:
    try:
        finished_summary = build_finished_summary(scrape_summary, scrape_response)
        finished_report = build_scrape_report(finished_summary, scrape_response)
        return finished_report, list(finished_report.jobs)
    except Exception:
        LOG.exception("scrape %s returned a result that could not be read", scrape_summary.id)
        return _build_failed_outcome(scrape_summary, SCRAPE_FAILED_MESSAGE)


def _build_no_jobs_text(scrape_summary: ScrapeSummary) -> str:
    keywords = ", ".join(scrape_summary.keywords)
    sites = ", ".join(scrape_summary.sites)
    if scrape_summary.error:
        failed_lead = f"Run failed for {keywords} on {sites}"
        return _truncate_discord_text(failed_lead, f": {scrape_summary.error}")
    return _truncate_discord_text(f"{keywords} on {sites} found 0 jobs")


def _truncate_discord_text(lead: str, tail: str = "") -> str:
    limit = MAX_TEXT_CHARS - DISCORD_MENTION_RESERVE
    kept_tail = tail[:limit]
    return lead[: limit - len(kept_tail)] + kept_tail


def _build_digest_counts(scrape_summary: ScrapeSummary) -> dict[str, int]:
    return {
        "keyword_count": len(scrape_summary.keywords),
        "site_count": len(scrape_summary.sites),
        "error_count": scrape_summary.error_count,
    }


def _build_send_error_message(scrape_id: str, exc: Exception) -> str:
    if isinstance(exc, DISCORD_KNOWN_ERRORS):
        return exc.message
    LOG.error("scrape %s discord send failed", scrape_id, exc_info=exc)
    return DISCORD_SEND_FAILED_MESSAGE


def _count_delivered_jobs(discord_delivery: dict[str, Any]) -> tuple[int, int]:
    sent = 0
    failed = 0
    for delivery_entry in discord_delivery["results"]:
        job_count = _count_jobs_in_delivery_entry(delivery_entry)
        if delivery_entry["status"] == "failed":
            failed += job_count
        else:
            sent += job_count
    return sent, failed


def _count_jobs_in_delivery_entry(delivery_entry: dict[str, Any]) -> int:
    if delivery_entry["kind"] == "file":
        return delivery_entry["job_count"]
    return 1


def _pick_discord_status(sent: int, failed: int) -> DiscordStatus:
    if sent == 0:
        return DiscordStatus.FAILED
    if failed > 0:
        return DiscordStatus.PARTIAL
    return DiscordStatus.SENT
