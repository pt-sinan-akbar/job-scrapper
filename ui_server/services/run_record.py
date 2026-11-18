from __future__ import annotations

import secrets
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class RunStatus(StrEnum):
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
class RunRecord:
    id: str
    status: RunStatus
    keywords: tuple[str, ...]
    sites: tuple[str, ...]
    started_at: str
    finished_at: str | None = None
    job_count: int = 0
    error_count: int = 0
    error: str | None = None
    discord_status: DiscordStatus | None = None
    discord_sent: int = 0
    discord_failed: int = 0
    discord_error: str | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def flatten_jobs(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        job
        for group in result.get("results", [])
        for site in group.get("sites", [])
        for job in site.get("jobs", [])
    ]


def _status_for(result: dict[str, Any], job_count: int) -> RunStatus:
    if result.get("ok"):
        return RunStatus.SUCCEEDED
    return RunStatus.PARTIAL if job_count > 0 else RunStatus.FAILED


def new_run(keywords: tuple[str, ...], sites: tuple[str, ...]) -> RunRecord:
    now = _now()
    return RunRecord(
        id=f"{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(3)}",
        status=RunStatus.RUNNING,
        keywords=keywords,
        sites=sites,
        started_at=now.isoformat(),
    )


def finish_run(record: RunRecord, result: dict[str, Any]) -> RunRecord:
    job_count = len(flatten_jobs(result))
    return replace(
        record,
        status=_status_for(result, job_count),
        finished_at=_now().isoformat(),
        job_count=job_count,
        error_count=len(result.get("errors", [])),
    )


def fail_run(record: RunRecord, message: str) -> RunRecord:
    return replace(record, status=RunStatus.FAILED, finished_at=_now().isoformat(), error=message)


def with_discord(
    record: RunRecord,
    status: DiscordStatus,
    sent: int = 0,
    failed: int = 0,
    error: str | None = None,
) -> RunRecord:
    return replace(
        record,
        discord_status=status,
        discord_sent=sent,
        discord_failed=failed,
        discord_error=error,
    )
