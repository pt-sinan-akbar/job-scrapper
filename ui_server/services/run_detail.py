from __future__ import annotations

import math
from dataclasses import asdict, dataclass, fields
from enum import Enum
from typing import Any

from ui_server.services.run_record import DiscordStatus, RunRecord, RunStatus

JOB_FIELDS = ("title", "company", "location", "url", "posted_at")
JOB_LEAD_FIELDS = ("site", "matched_keyword", *JOB_FIELDS)
FAILURE_FIELDS = ("keyword", "site", "reason")
RECORD_FIELDS = tuple(field.name for field in fields(RunRecord))

Pair = tuple[str, str]


@dataclass(frozen=True)
class RunDetail:
    record: RunRecord
    jobs: tuple[dict[str, Any], ...] = ()
    failures: tuple[dict[str, Any], ...] = ()
    payloads: tuple[dict[str, Any], ...] = ()


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _job_view(job: dict[str, Any], keyword: Any, site: Any) -> dict[str, Any]:
    view = {
        "site": job.get("site") or site,
        "matched_keyword": job.get("matched_keyword") or keyword,
        **{name: job.get(name) for name in JOB_FIELDS},
        **{name: value for name, value in job.items() if name not in JOB_LEAD_FIELDS},
    }
    return _json_safe(view)


def build_jobs(result: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    return tuple(
        _job_view(job, group.get("keyword"), site.get("site"))
        for group in result.get("results", [])
        for site in group.get("sites", [])
        for job in site.get("jobs", [])
    )


def build_failures(result: dict[str, Any]) -> tuple[dict[str, str | None], ...]:
    return tuple(
        {name: _text(error.get(name)) for name in FAILURE_FIELDS}
        for error in result.get("errors", [])
        if isinstance(error, dict)
    )


def _payload_files(result: dict[str, Any], key: str) -> dict[Pair, dict[str, Any]]:
    entries = result.get(key)
    if not isinstance(entries, list):
        return {}
    return {
        (entry["keyword"], entry["site"]): entry["payload"]
        for entry in entries
        if isinstance(entry, dict)
        and isinstance(entry.get("keyword"), str)
        and isinstance(entry.get("site"), str)
        and isinstance(entry.get("payload"), dict)
    }


def _ordered_pairs(stored: list[Pair], record: RunRecord) -> list[Pair]:
    known = [(keyword, site) for keyword in record.keywords for site in record.sites]
    known_set = set(known)
    stored_set = set(stored)
    return [pair for pair in known if pair in stored_set] + [
        pair for pair in stored if pair not in known_set
    ]


def build_payloads(result: dict[str, Any], record: RunRecord) -> tuple[dict[str, Any], ...]:
    raw = _payload_files(result, "raw_results")
    filtered = _payload_files(result, "filtered_results")
    stored = list(dict.fromkeys([*raw, *filtered]))
    return tuple(
        {"keyword": pair[0], "site": pair[1], "raw": raw.get(pair), "filtered": filtered.get(pair)}
        for pair in _ordered_pairs(stored, record)
    )


def build_detail(record: RunRecord, result: dict[str, Any]) -> RunDetail:
    return RunDetail(
        record=record,
        jobs=build_jobs(result),
        failures=build_failures(result),
        payloads=build_payloads(result, record),
    )


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return list(value)
    return value


def record_to_dict(record: RunRecord) -> dict[str, Any]:
    return {name: _plain(value) for name, value in asdict(record).items()}


def detail_to_response(detail: RunDetail) -> dict[str, Any]:
    return {
        "record": record_to_dict(detail.record),
        "jobs": list(detail.jobs),
        "failures": list(detail.failures),
    }


def detail_to_dict(detail: RunDetail) -> dict[str, Any]:
    return {**detail_to_response(detail), "payloads": list(detail.payloads)}


def record_from_dict(data: dict[str, Any]) -> RunRecord:
    values = {name: data[name] for name in RECORD_FIELDS if name in data}
    discord_status = values.get("discord_status")
    return RunRecord(
        **{
            **values,
            "status": RunStatus(values["status"]),
            "discord_status": None if discord_status is None else DiscordStatus(discord_status),
            "keywords": tuple(values["keywords"]),
            "sites": tuple(values["sites"]),
        }
    )


def detail_from_dict(document: dict[str, Any]) -> RunDetail:
    return RunDetail(
        record=record_from_dict(document["record"]),
        jobs=tuple(document.get("jobs", [])),
        failures=tuple(document.get("failures", [])),
        payloads=tuple(document.get("payloads", [])),
    )
