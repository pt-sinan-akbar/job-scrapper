from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from backend.services.scrape_report import (
    ScrapeReport,
    build_payloads,
    build_report_response,
    build_scrape_report,
    convert_report_to_document,
    read_report_from_document,
)
from backend.services.scrape_summary import DiscordStatus, ScrapeStatus, ScrapeSummary

SCRAPE_SUMMARY = ScrapeSummary(
    id="20261118T010000Z-abc123",
    status=ScrapeStatus.PARTIAL,
    keywords=("django", "flask"),
    sites=("upwork", "glints"),
    started_at="2026-11-18T01:00:00+00:00",
    finished_at="2026-11-18T01:02:00+00:00",
    job_count=2,
    error_count=1,
    discord_status=DiscordStatus.SENT,
    discord_sent=2,
)
FULL_JOB = {
    "site": "upwork",
    "matched_keyword": "django",
    "title": "Django dev",
    "company": "Acme",
    "location": "Remote",
    "url": "https://example.com/1",
    "posted_at": "2026-11-17T10:00:00+00:00",
    "salary": "100",
    "salary_min": 100,
    "salary_max": None,
    "work_type": "remote",
    "requirements": ["python", "sql"],
}
UNORDERED_JOB = {
    "salary_min": 5,
    "url": "https://example.com/2",
    "company_id": "c-9",
    "site": "",
    "title": "Mixed",
    "matched_keyword": None,
    "job_id": 42,
}
BARE_JOB = {"title": "Bare", "posted_at": 1731800000}
FAILED_PAYLOAD = {"error": "timeout", "keyword": "flask", "jobs": [{"title": "Never shown"}]}
RESULT: dict[str, Any] = {
    "ok": False,
    "results": [
        {"keyword": "flask", "site": "glints", "payload": {"jobs": []}},
        {"keyword": "django", "site": "upwork", "payload": {"jobs": [FULL_JOB]}},
        {"keyword": "django", "site": "glints", "payload": {"jobs": [BARE_JOB]}},
        {"keyword": "django", "site": "kalibrr", "payload": {"jobs": [UNORDERED_JOB]}},
        {"keyword": "flask", "site": "upwork", "payload": FAILED_PAYLOAD},
    ],
    "errors": [{"keyword": "flask", "site": "upwork", "reason": "timeout", "attempts": []}],
    "raw_results": [
        {"keyword": "flask", "site": "glints", "payload": {"jobs": [3, 4]}},
        {"keyword": "django", "site": "upwork", "payload": {"jobs": [1, 2]}},
        {"keyword": "go", "site": "upwork", "payload": {"jobs": [5]}},
    ],
    "filtered_results": [
        {"keyword": "rust", "site": "upwork", "payload": {"jobs": [6]}},
    ],
}


def test_jobs_keep_every_source_key_with_original_values():
    scrape_report = build_scrape_report(SCRAPE_SUMMARY, RESULT)

    assert scrape_report.jobs[0] == FULL_JOB
    assert scrape_report.jobs[0]["salary_min"] == 100
    assert scrape_report.jobs[0]["requirements"] == ["python", "sql"]


def test_jobs_fall_back_to_group_keyword_and_site_and_fill_display_fields():
    scrape_report = build_scrape_report(SCRAPE_SUMMARY, RESULT)

    assert scrape_report.jobs[1] == {
        "site": "glints",
        "matched_keyword": "django",
        "title": "Bare",
        "company": None,
        "location": None,
        "url": None,
        "posted_at": 1731800000,
    }


def test_jobs_put_site_keyword_and_display_fields_first_then_the_rest_in_order():
    scrape_report = build_scrape_report(SCRAPE_SUMMARY, RESULT)

    assert list(scrape_report.jobs[2].items()) == [
        ("site", "kalibrr"),
        ("matched_keyword", "django"),
        ("title", "Mixed"),
        ("company", None),
        ("location", None),
        ("url", "https://example.com/2"),
        ("posted_at", None),
        ("salary_min", 5),
        ("company_id", "c-9"),
        ("job_id", 42),
    ]


def test_jobs_are_new_dicts_and_the_result_is_left_unchanged():
    result = deepcopy(RESULT)

    scrape_report = build_scrape_report(SCRAPE_SUMMARY, result)

    assert result == RESULT
    assert scrape_report.jobs[0] is not result["results"][1]["payload"]["jobs"][0]
    assert list(result["results"][3]["payload"]["jobs"][0]) == list(UNORDERED_JOB)


def test_jobs_copy_nested_values_instead_of_sharing_them():
    tags = ["python", {"level": "senior"}]
    payload = {"jobs": [{"tags": tags}]}
    result = {"results": [{"keyword": "django", "site": "upwork", "payload": payload}]}

    job = build_scrape_report(SCRAPE_SUMMARY, result).jobs[0]

    assert job["tags"] == tags
    assert job["tags"] is not tags
    assert job["tags"][1] is not tags[1]


def test_jobs_replace_numbers_json_cannot_carry_with_none():
    source = {
        "salary_min": float("nan"),
        "salary_max": float("inf"),
        "rates": [1.5, float("-inf")],
        "extra": {"score": float("nan")},
    }
    result = {"results": [{"keyword": "django", "site": "upwork", "payload": {"jobs": [source]}}]}

    job = build_scrape_report(SCRAPE_SUMMARY, result).jobs[0]

    assert job["salary_min"] is None
    assert job["salary_max"] is None
    assert job["rates"] == [1.5, None]
    assert job["extra"] == {"score": None}


def test_jobs_come_only_from_results_whose_payload_has_no_error():
    scrape_report = build_scrape_report(SCRAPE_SUMMARY, RESULT)

    assert [job["title"] for job in scrape_report.jobs] == ["Django dev", "Bare", "Mixed"]


def test_jobs_and_payloads_ignore_the_old_filtered_results_key():
    job = {"title": "Flat"}
    result = {
        "results": [{"keyword": "django", "site": "upwork", "payload": {"jobs": [job]}}],
        "filtered_results": [
            {"keyword": "django", "site": "glints", "payload": {"jobs": [{"title": "Old"}]}}
        ],
    }

    scrape_report = build_scrape_report(SCRAPE_SUMMARY, result)

    assert [job["title"] for job in scrape_report.jobs] == ["Flat"]
    assert [payload["site"] for payload in scrape_report.payloads] == ["upwork"]


def test_failures_keep_keyword_site_and_reason():
    scrape_report = build_scrape_report(SCRAPE_SUMMARY, RESULT)

    assert scrape_report.failures == ({"keyword": "flask", "site": "upwork", "reason": "timeout"},)


def test_payloads_follow_record_order_then_extra_pairs():
    scrape_report = build_scrape_report(SCRAPE_SUMMARY, RESULT)

    assert scrape_report.payloads == (
        {"keyword": "django", "site": "upwork", "filtered": {"jobs": [FULL_JOB]}},
        {"keyword": "django", "site": "glints", "filtered": {"jobs": [BARE_JOB]}},
        {"keyword": "flask", "site": "upwork", "filtered": FAILED_PAYLOAD},
        {"keyword": "flask", "site": "glints", "filtered": {"jobs": []}},
        {"keyword": "django", "site": "kalibrr", "filtered": {"jobs": [UNORDERED_JOB]}},
    )


def test_payloads_skip_entries_that_are_not_keyword_site_payload_dicts():
    result = {
        "results": [
            {"keyword": "django", "site": "upwork", "payload": {"jobs": [1]}},
            {"keyword": "django", "site": "glints", "payload": "not a dict"},
            {"keyword": None, "site": "glints", "payload": {"jobs": [2]}},
            "not an entry",
        ]
    }

    payloads = build_payloads(result, SCRAPE_SUMMARY)

    assert payloads == ({"keyword": "django", "site": "upwork", "filtered": {"jobs": [1]}},)


def test_payloads_leave_raw_results_out():
    scrape_report = build_scrape_report(SCRAPE_SUMMARY, RESULT)

    assert all(
        set(payload) == {"keyword", "site", "filtered"} for payload in scrape_report.payloads
    )
    assert all(
        "raw" not in payload for payload in convert_report_to_document(scrape_report)["payloads"]
    )


def test_pairs_outside_results_get_no_payload():
    scrape_report = build_scrape_report(SCRAPE_SUMMARY, RESULT)

    stored_pairs = [(payload["keyword"], payload["site"]) for payload in scrape_report.payloads]

    assert ("go", "upwork") not in stored_pairs
    assert ("rust", "upwork") not in stored_pairs


def test_empty_result_gives_empty_lists():
    assert build_scrape_report(SCRAPE_SUMMARY, {}) == ScrapeReport(SCRAPE_SUMMARY)


def test_convert_report_to_document_uses_plain_values():
    data = convert_report_to_document(build_scrape_report(SCRAPE_SUMMARY, RESULT))

    assert set(data) == {"record", "jobs", "failures", "payloads"}
    assert data["record"]["status"] == "partial"
    assert type(data["record"]["status"]) is str
    assert data["record"]["discord_status"] == "sent"
    assert data["record"]["keywords"] == ["django", "flask"]
    assert isinstance(data["jobs"], list)
    assert isinstance(data["payloads"], list)


def test_build_report_response_leaves_payloads_out():
    scrape_report = build_scrape_report(SCRAPE_SUMMARY, RESULT)

    data = build_report_response(scrape_report)
    stored = convert_report_to_document(scrape_report)

    assert list(data) == ["record", "jobs", "failures"]
    assert data == {name: stored[name] for name in data}
    assert stored["payloads"] == list(scrape_report.payloads)


def test_detail_round_trips_through_a_stored_document():
    scrape_report = build_scrape_report(SCRAPE_SUMMARY, RESULT)
    document = {
        **convert_report_to_document(scrape_report),
        "_id": SCRAPE_SUMMARY.id,
        "saved_at": "x",
    }

    assert read_report_from_document(document) == scrape_report


def test_old_stored_document_with_display_only_jobs_still_loads():
    old_job = {
        "site": "upwork",
        "matched_keyword": "django",
        "title": "Old",
        "company": None,
        "location": None,
        "url": None,
        "posted_at": "1731800000",
    }
    payload = {"keyword": "django", "site": "upwork", "raw": {"a": 1}, "filtered": None}
    document = {
        **convert_report_to_document(ScrapeReport(SCRAPE_SUMMARY)),
        "_id": SCRAPE_SUMMARY.id,
        "jobs": [old_job],
        "payloads": [payload],
    }

    assert read_report_from_document(document) == ScrapeReport(
        SCRAPE_SUMMARY, (old_job,), (), (payload,)
    )


def test_old_stored_document_with_raw_payload_still_loads_and_answers():
    old_payload = {
        "keyword": "django",
        "site": "upwork",
        "raw": {"jobs": [1, 2]},
        "filtered": {"jobs": [1]},
    }
    document = {
        **convert_report_to_document(build_scrape_report(SCRAPE_SUMMARY, RESULT)),
        "_id": SCRAPE_SUMMARY.id,
        "saved_at": "x",
        "payloads": [old_payload],
    }

    scrape_report = read_report_from_document(document)

    assert scrape_report.summary == SCRAPE_SUMMARY
    assert scrape_report.payloads == (old_payload,)
    assert build_report_response(scrape_report) == build_report_response(
        build_scrape_report(SCRAPE_SUMMARY, RESULT)
    )


@pytest.mark.parametrize(
    "document",
    [
        {},
        {"record": {"id": "x"}},
        {
            "record": {
                **convert_report_to_document(ScrapeReport(SCRAPE_SUMMARY))["record"],
                "status": "odd",
            }
        },
    ],
)
def test_unreadable_document_raises(document: dict):
    with pytest.raises((KeyError, TypeError, ValueError)):
        read_report_from_document(document)
