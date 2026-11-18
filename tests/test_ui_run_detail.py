from __future__ import annotations

import pytest

from ui_server.services.run_detail import (
    RunDetail,
    build_detail,
    detail_from_dict,
    detail_to_dict,
)
from ui_server.services.run_record import DiscordStatus, RunRecord, RunStatus

RECORD = RunRecord(
    id="20261118T010000Z-abc123",
    status=RunStatus.PARTIAL,
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
}
RESULT = {
    "ok": False,
    "results": [
        {
            "keyword": "django",
            "sites": [
                {"site": "upwork", "jobs": [FULL_JOB]},
                {"site": "glints", "jobs": [{"title": "Bare", "posted_at": 1731800000}]},
            ],
        }
    ],
    "errors": [{"keyword": "flask", "site": "upwork", "reason": "timeout", "attempts": []}],
    "raw_results": [
        {"keyword": "flask", "site": "glints", "payload": {"jobs": [3]}},
        {"keyword": "django", "site": "upwork", "payload": {"jobs": [1, 2]}},
        {"keyword": "rust", "site": "upwork", "payload": {"jobs": []}},
        {"keyword": "django", "site": "upwork", "payload": "not a dict"},
    ],
    "filtered_results": [
        {"keyword": "django", "site": "upwork", "payload": {"jobs": [1]}},
    ],
}


def test_jobs_keep_only_the_display_fields():
    detail = build_detail(RECORD, RESULT)

    assert detail.jobs[0] == {
        "site": "upwork",
        "matched_keyword": "django",
        "title": "Django dev",
        "company": "Acme",
        "location": "Remote",
        "url": "https://example.com/1",
        "posted_at": "2026-11-17T10:00:00+00:00",
    }


def test_jobs_fall_back_to_group_keyword_and_site_and_use_text_values():
    detail = build_detail(RECORD, RESULT)

    assert detail.jobs[1] == {
        "site": "glints",
        "matched_keyword": "django",
        "title": "Bare",
        "company": None,
        "location": None,
        "url": None,
        "posted_at": "1731800000",
    }


def test_failures_keep_keyword_site_and_reason():
    detail = build_detail(RECORD, RESULT)

    assert detail.failures == ({"keyword": "flask", "site": "upwork", "reason": "timeout"},)


def test_payloads_follow_record_order_then_extra_pairs():
    detail = build_detail(RECORD, RESULT)

    assert detail.payloads == (
        {"keyword": "django", "site": "upwork", "raw": {"jobs": [1, 2]}, "filtered": {"jobs": [1]}},
        {"keyword": "flask", "site": "glints", "raw": {"jobs": [3]}, "filtered": None},
        {"keyword": "rust", "site": "upwork", "raw": {"jobs": []}, "filtered": None},
    )


def test_empty_result_gives_empty_lists():
    assert build_detail(RECORD, {}) == RunDetail(RECORD)


def test_detail_to_dict_uses_plain_values():
    data = detail_to_dict(build_detail(RECORD, RESULT))

    assert set(data) == {"record", "jobs", "failures", "payloads"}
    assert data["record"]["status"] == "partial"
    assert type(data["record"]["status"]) is str
    assert data["record"]["discord_status"] == "sent"
    assert data["record"]["keywords"] == ["django", "flask"]
    assert isinstance(data["jobs"], list)
    assert isinstance(data["payloads"], list)


def test_detail_round_trips_through_a_stored_document():
    detail = build_detail(RECORD, RESULT)
    document = {**detail_to_dict(detail), "_id": RECORD.id, "saved_at": "x"}

    assert detail_from_dict(document) == detail


@pytest.mark.parametrize(
    "document",
    [
        {},
        {"record": {"id": "x"}},
        {"record": {**detail_to_dict(RunDetail(RECORD))["record"], "status": "odd"}},
    ],
)
def test_unreadable_document_raises(document: dict):
    with pytest.raises((KeyError, TypeError, ValueError)):
        detail_from_dict(document)
