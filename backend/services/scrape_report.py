from __future__ import annotations

import math
from dataclasses import asdict, dataclass, fields
from enum import Enum
from typing import Any

from backend.services.scrape_summary import DiscordStatus, ScrapeStatus, ScrapeSummary
from mcp_server.server import list_successful_result_entries

JOB_FIELDS = ("title", "company", "location", "url", "posted_at")
JOB_LEAD_FIELDS = ("site", "matched_keyword", *JOB_FIELDS)
FAILURE_FIELDS = ("keyword", "site", "reason")
SUMMARY_FIELDS = tuple(summary_field.name for summary_field in fields(ScrapeSummary))

Pair = tuple[str, str]


@dataclass(frozen=True)
class ScrapeReport:
    summary: ScrapeSummary
    jobs: tuple[dict[str, Any], ...] = ()
    failures: tuple[dict[str, Any], ...] = ()
    payloads: tuple[dict[str, Any], ...] = ()


def build_scrape_report(
    scrape_summary: ScrapeSummary, scrape_response: dict[str, Any]
) -> ScrapeReport:
    return ScrapeReport(
        summary=scrape_summary,
        jobs=build_jobs(scrape_response),
        failures=build_failures(scrape_response),
        payloads=build_payloads(scrape_response, scrape_summary),
    )


def build_jobs(scrape_response: dict[str, Any]) -> tuple[dict[str, Any], ...]:
    jobs: list[dict[str, Any]] = []
    for result_entry in list_successful_result_entries(scrape_response.get("results", [])):
        keyword = result_entry.get("keyword")
        site = result_entry.get("site")
        for job in result_entry["payload"].get("jobs", []):
            jobs.append(_build_job_entry(job, keyword, site))
    return tuple(jobs)


def build_failures(scrape_response: dict[str, Any]) -> tuple[dict[str, str | None], ...]:
    failures: list[dict[str, str | None]] = []
    for error in scrape_response.get("errors", []):
        if not isinstance(error, dict):
            continue
        failures.append(_build_failure_entry(error))
    return tuple(failures)


def build_payloads(
    scrape_response: dict[str, Any], scrape_summary: ScrapeSummary
) -> tuple[dict[str, Any], ...]:
    payloads_by_pair = _read_payloads_by_pair(scrape_response)
    payloads: list[dict[str, Any]] = []
    for keyword, site in _order_pairs_by_summary(list(payloads_by_pair), scrape_summary):
        filtered_payload = payloads_by_pair[(keyword, site)]
        payloads.append({"keyword": keyword, "site": site, "filtered": filtered_payload})
    return tuple(payloads)


def convert_summary_to_dict(scrape_summary: ScrapeSummary) -> dict[str, Any]:
    summary_dict: dict[str, Any] = {}
    for field_name, field_value in asdict(scrape_summary).items():
        summary_dict[field_name] = _convert_to_plain_value(field_value)
    return summary_dict


def build_report_response(scrape_report: ScrapeReport) -> dict[str, Any]:
    return {
        "record": convert_summary_to_dict(scrape_report.summary),
        "jobs": list(scrape_report.jobs),
        "failures": list(scrape_report.failures),
    }


def convert_report_to_document(scrape_report: ScrapeReport) -> dict[str, Any]:
    report_document = build_report_response(scrape_report)
    report_document["payloads"] = list(scrape_report.payloads)
    return report_document


def read_summary_from_dict(stored_summary: dict[str, Any]) -> ScrapeSummary:
    summary_fields = _pick_summary_fields(stored_summary)
    summary_fields["status"] = ScrapeStatus(summary_fields["status"])
    summary_fields["discord_status"] = _read_discord_status(summary_fields.get("discord_status"))
    summary_fields["keywords"] = tuple(summary_fields["keywords"])
    summary_fields["sites"] = tuple(summary_fields["sites"])
    return ScrapeSummary(**summary_fields)


def read_report_from_document(document: dict[str, Any]) -> ScrapeReport:
    return ScrapeReport(
        summary=read_summary_from_dict(document["record"]),
        jobs=tuple(document.get("jobs", [])),
        failures=tuple(document.get("failures", [])),
        payloads=tuple(document.get("payloads", [])),
    )


def _convert_to_text(raw_value: Any) -> str | None:
    if raw_value is None:
        return None
    return str(raw_value)


def _make_json_safe(raw_value: Any) -> Any:
    if isinstance(raw_value, float) and not math.isfinite(raw_value):
        return None
    if isinstance(raw_value, dict):
        return _make_dict_json_safe(raw_value)
    if isinstance(raw_value, list):
        return _make_list_json_safe(raw_value)
    return raw_value


def _make_dict_json_safe(raw_dict: dict[Any, Any]) -> dict[Any, Any]:
    safe_dict: dict[Any, Any] = {}
    for key, nested_value in raw_dict.items():
        safe_dict[key] = _make_json_safe(nested_value)
    return safe_dict


def _make_list_json_safe(raw_list: list[Any]) -> list[Any]:
    safe_list: list[Any] = []
    for nested_value in raw_list:
        safe_list.append(_make_json_safe(nested_value))
    return safe_list


def _build_job_entry(job: dict[str, Any], keyword: Any, site: Any) -> dict[str, Any]:
    job_entry: dict[str, Any] = {
        "site": job.get("site") or site,
        "matched_keyword": job.get("matched_keyword") or keyword,
    }
    for field_name in JOB_FIELDS:
        job_entry[field_name] = job.get(field_name)
    for field_name, field_value in job.items():
        if field_name in JOB_LEAD_FIELDS:
            continue
        job_entry[field_name] = field_value
    return _make_json_safe(job_entry)


def _build_failure_entry(error: dict[str, Any]) -> dict[str, str | None]:
    failure_entry: dict[str, str | None] = {}
    for field_name in FAILURE_FIELDS:
        failure_entry[field_name] = _convert_to_text(error.get(field_name))
    return failure_entry


def _read_payloads_by_pair(scrape_response: dict[str, Any]) -> dict[Pair, dict[str, Any]]:
    result_entries = scrape_response.get("results")
    if not isinstance(result_entries, list):
        return {}
    payloads_by_pair: dict[Pair, dict[str, Any]] = {}
    for result_entry in result_entries:
        if not _is_readable_result_entry(result_entry):
            continue
        pair = (result_entry["keyword"], result_entry["site"])
        payloads_by_pair[pair] = result_entry["payload"]
    return payloads_by_pair


def _is_readable_result_entry(result_entry: Any) -> bool:
    if not isinstance(result_entry, dict):
        return False
    if not isinstance(result_entry.get("keyword"), str):
        return False
    if not isinstance(result_entry.get("site"), str):
        return False
    return isinstance(result_entry.get("payload"), dict)


def _order_pairs_by_summary(stored_pairs: list[Pair], scrape_summary: ScrapeSummary) -> list[Pair]:
    requested_pairs = _list_requested_pairs(scrape_summary)
    requested_pair_set = set(requested_pairs)
    stored_pair_set = set(stored_pairs)
    ordered_pairs: list[Pair] = []
    for pair in requested_pairs:
        if pair in stored_pair_set:
            ordered_pairs.append(pair)
    for pair in stored_pairs:
        if pair not in requested_pair_set:
            ordered_pairs.append(pair)
    return ordered_pairs


def _list_requested_pairs(scrape_summary: ScrapeSummary) -> list[Pair]:
    requested_pairs: list[Pair] = []
    for keyword in scrape_summary.keywords:
        for site in scrape_summary.sites:
            requested_pairs.append((keyword, site))
    return requested_pairs


def _convert_to_plain_value(field_value: Any) -> Any:
    if isinstance(field_value, Enum):
        return field_value.value
    if isinstance(field_value, tuple):
        return list(field_value)
    return field_value


def _pick_summary_fields(stored_summary: dict[str, Any]) -> dict[str, Any]:
    summary_fields: dict[str, Any] = {}
    for field_name in SUMMARY_FIELDS:
        if field_name in stored_summary:
            summary_fields[field_name] = stored_summary[field_name]
    return summary_fields


def _read_discord_status(stored_status: Any) -> DiscordStatus | None:
    if stored_status is None:
        return None
    return DiscordStatus(stored_status)
