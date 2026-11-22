from __future__ import annotations

import secrets
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from mcp_server.server import list_successful_result_entries


class ScrapeStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class DiscordStatus(StrEnum):
    SENDING = "sending"
    SENT = "sent"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass(frozen=True)
class ScrapeSummary:
    id: str
    status: ScrapeStatus
    keywords: tuple[str, ...]
    sites: tuple[str, ...]
    started_at: str
    location: str | None = None
    max_age_hours: int | None = None
    finished_at: str | None = None
    job_count: int = 0
    error_count: int = 0
    error: str | None = None
    discord_status: DiscordStatus | None = None
    discord_sent: int = 0
    discord_failed: int = 0
    discord_error: str | None = None


def build_running_summary(
    keywords: tuple[str, ...],
    sites: tuple[str, ...],
    location: str | None = None,
    max_age_hours: int | None = None,
) -> ScrapeSummary:
    started_at = _read_current_time()
    return ScrapeSummary(
        id=f"{started_at:%Y%m%dT%H%M%SZ}-{secrets.token_hex(3)}",
        status=ScrapeStatus.RUNNING,
        keywords=keywords,
        sites=sites,
        started_at=started_at.isoformat(),
        location=location,
        max_age_hours=max_age_hours,
    )


def build_finished_summary(
    scrape_summary: ScrapeSummary, scrape_response: dict[str, Any]
) -> ScrapeSummary:
    job_count = len(_list_successful_jobs(scrape_response))
    return replace(
        scrape_summary,
        status=_pick_finished_status(scrape_response, job_count),
        finished_at=_read_current_time().isoformat(),
        job_count=job_count,
        error_count=len(scrape_response.get("errors", [])),
    )


def build_failed_summary(scrape_summary: ScrapeSummary, message: str) -> ScrapeSummary:
    return replace(
        scrape_summary,
        status=ScrapeStatus.FAILED,
        finished_at=_read_current_time().isoformat(),
        error=message,
    )


def copy_summary_with_discord_status(
    scrape_summary: ScrapeSummary,
    status: DiscordStatus,
    sent: int = 0,
    failed: int = 0,
    error: str | None = None,
) -> ScrapeSummary:
    return replace(
        scrape_summary,
        discord_status=status,
        discord_sent=sent,
        discord_failed=failed,
        discord_error=error,
    )


def _read_current_time() -> datetime:
    return datetime.now(UTC)


def _list_successful_jobs(scrape_response: dict[str, Any]) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    for result_entry in list_successful_result_entries(scrape_response.get("results", [])):
        jobs.extend(result_entry["payload"].get("jobs", []))
    return jobs


def _pick_finished_status(scrape_response: dict[str, Any], job_count: int) -> ScrapeStatus:
    if scrape_response.get("ok"):
        return ScrapeStatus.SUCCEEDED
    if job_count > 0:
        return ScrapeStatus.PARTIAL
    return ScrapeStatus.FAILED
