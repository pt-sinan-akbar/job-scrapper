from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from ui_server.services.run_detail import (
    RunDetail,
    build_detail,
    detail_from_dict,
    detail_to_dict,
    detail_to_response,
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
RESULT: dict[str, Any] = {
    "ok": False,
    "results": [
        {
            "keyword": "django",
            "sites": [
                {"site": "upwork", "jobs": [FULL_JOB]},
                {"site": "glints", "jobs": [{"title": "Bare", "posted_at": 1731800000}]},
                {"site": "kalibrr", "jobs": [UNORDERED_JOB]},
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


def test_jobs_keep_every_source_key_with_original_values():
    detail = build_detail(RECORD, RESULT)

    assert detail.jobs[0] == FULL_JOB
    assert detail.jobs[0]["salary_min"] == 100
    assert detail.jobs[0]["requirements"] == ["python", "sql"]


def test_jobs_fall_back_to_group_keyword_and_site_and_fill_display_fields():
    detail = build_detail(RECORD, RESULT)

    assert detail.jobs[1] == {
        "site": "glints",
        "matched_keyword": "django",
        "title": "Bare",
        "company": None,
        "location": None,
        "url": None,
        "posted_at": 1731800000,
    }


def test_jobs_put_site_keyword_and_display_fields_first_then_the_rest_in_order():
    detail = build_detail(RECORD, RESULT)

    assert list(detail.jobs[2].items()) == [
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

    detail = build_detail(RECORD, result)

    assert result == RESULT
    assert detail.jobs[0] is not result["results"][0]["sites"][0]["jobs"][0]
    assert list(result["results"][0]["sites"][2]["jobs"][0]) == list(UNORDERED_JOB)


def test_jobs_copy_nested_values_instead_of_sharing_them():
    tags = ["python", {"level": "senior"}]
    result = {
        "results": [{"keyword": "django", "sites": [{"site": "upwork", "jobs": [{"tags": tags}]}]}]
    }

    job = build_detail(RECORD, result).jobs[0]

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
    result = {"results": [{"keyword": "django", "sites": [{"site": "upwork", "jobs": [source]}]}]}

    job = build_detail(RECORD, result).jobs[0]

    assert job["salary_min"] is None
    assert job["salary_max"] is None
    assert job["rates"] == [1.5, None]
    assert job["extra"] == {"score": None}


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


def test_detail_to_response_leaves_payloads_out():
    detail = build_detail(RECORD, RESULT)

    data = detail_to_response(detail)
    stored = detail_to_dict(detail)

    assert list(data) == ["record", "jobs", "failures"]
    assert data == {name: stored[name] for name in data}
    assert stored["payloads"] == list(detail.payloads)


def test_detail_round_trips_through_a_stored_document():
    detail = build_detail(RECORD, RESULT)
    document = {**detail_to_dict(detail), "_id": RECORD.id, "saved_at": "x"}

    assert detail_from_dict(document) == detail


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
        **detail_to_dict(RunDetail(RECORD)),
        "_id": RECORD.id,
        "jobs": [old_job],
        "payloads": [payload],
    }

    assert detail_from_dict(document) == RunDetail(RECORD, (old_job,), (), (payload,))


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
