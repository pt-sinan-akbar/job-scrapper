from __future__ import annotations

from types import MappingProxyType
from typing import Any
from unittest.mock import MagicMock, patch

from scraper.job_settings import SettingsMissingError
from scraper.runner import RunResult, SitePayloads, pair_error
from scraper.types import JOB_FIELD_ORDER

KEYWORD = "data analyst"
SITE = "jobstreet"
EMPTY_RAW: dict[str, Any] = {"keyword": KEYWORD, "count": 0, "jobs": []}


def _make_config(keyword: str = KEYWORD, site: str = SITE):
    cfg = MagicMock()
    cfg.keywords = (keyword,)
    cfg.enabled_site_names.return_value = (site,)
    return cfg


def _run_result(filtered: dict[str, Any], raw: dict[str, Any] | None = None) -> RunResult:
    payloads = SitePayloads(filtered=filtered, raw=raw if raw is not None else EMPTY_RAW)
    return RunResult(exit_code=0, results=MappingProxyType({(KEYWORD, SITE): payloads}))


def _scrape_with(run_result: RunResult, **kwargs: Any) -> dict[str, Any]:
    from mcp_server.server import scrape_jobs

    with (
        patch("mcp_server.server._load_config", return_value=_make_config()),
        patch("mcp_server.server.run_scraper", return_value=run_result),
    ):
        return scrape_jobs(keywords=[KEYWORD], sites=[SITE], **kwargs)


def _filtered(jobs: list[dict[str, Any]], max_age_hours: int | None = 24) -> dict[str, Any]:
    return {
        "keyword": KEYWORD,
        "fields": ["title"],
        "count": len(jobs),
        "jobs": jobs,
        "max_age_hours": max_age_hours,
        "filter": None,
    }


FETCH_FAILED = {"error": "fetch failed", "url": "https://example.com", "keyword": KEYWORD}


@patch("mcp_server.server.mongo")
def test_ok_true_when_zero_jobs(mock_mongo):
    result = _scrape_with(_run_result(_filtered([])))

    assert result["ok"] is True
    assert result["errors"] == []
    assert result["results"][0]["sites"][0]["count"] == 0


@patch("mcp_server.server.mongo")
def test_ok_true_when_jobs_found(mock_mongo):
    result = _scrape_with(_run_result(_filtered([{"title": "A"}, {"title": "B"}])))

    assert result["ok"] is True
    assert result["errors"] == []
    assert result["results"][0]["sites"][0]["count"] == 2


@patch("mcp_server.server.mongo")
def test_ok_false_when_fetch_failed(mock_mongo):
    result = _scrape_with(_run_result(FETCH_FAILED))

    assert result["ok"] is False
    assert len(result["errors"]) == 1
    assert result["errors"][0]["reason"] == "fetch failed"
    assert result["results"][0]["sites"] == []


@patch("mcp_server.server.mongo")
def test_fetch_failure_attempts_are_reported(mock_mongo):
    attempts = [{"fetcher": "curl_cffi", "code": "http_403", "detail": None}]
    result = _scrape_with(_run_result({**FETCH_FAILED, "attempts": attempts}))

    assert result["errors"][0]["attempts"] == attempts


@patch("mcp_server.server.mongo")
def test_ok_false_when_pair_missing_from_run_result(mock_mongo):
    result = _scrape_with(RunResult(exit_code=1))

    assert result["ok"] is False
    assert result["exit_code"] == 1
    assert result["errors"] == [
        {
            "keyword": KEYWORD,
            "site": SITE,
            "reason": "scraper returned no result for this pair (exit code 1)",
        }
    ]
    assert result["results"][0]["sites"] == []


@patch("mcp_server.server.mongo")
def test_selection_error_reason_is_reported_for_every_pair(mock_mongo):
    result = _scrape_with(RunResult(exit_code=1, error="no keywords to scrape"))

    assert result["ok"] is False
    assert result["errors"] == [
        {"keyword": KEYWORD, "site": SITE, "reason": "no keywords to scrape"}
    ]


@patch("mcp_server.server.mongo")
def test_skipped_or_crashed_pair_is_reported_as_error(mock_mongo):
    payloads = pair_error(KEYWORD, "crashed: RuntimeError")
    run_result = RunResult(exit_code=0, results=MappingProxyType({(KEYWORD, SITE): payloads}))
    mock_mongo.insert_run.return_value = "id1"

    result = _scrape_with(run_result)

    assert result["ok"] is False
    assert result["errors"][0]["reason"] == "crashed: RuntimeError"
    doc = mock_mongo.insert_run.call_args.args[0]
    assert doc["filtered_results"][0]["payload"]["error"] == "crashed: RuntimeError"
    assert doc["raw_results"][0]["payload"]["jobs"] == []


@patch("mcp_server.server.mongo")
@patch("mcp_server.server._write_status")
def test_scrape_jobs_writes_status(mock_write_status, mock_mongo):
    _scrape_with(_run_result(_filtered([{"title": "A"}], max_age_hours=None)))

    mock_write_status.assert_called_once()
    result_arg, duration_arg = mock_write_status.call_args.args
    assert result_arg["ok"] is True
    assert isinstance(duration_arg, float)


@patch("mcp_server.server.mongo")
def test_scrape_jobs_normalizes_jobs_to_canonical_schema(mock_mongo):
    filtered = {
        **_filtered(
            [
                {
                    "title": "Data Analyst",
                    "company": "ACME",
                    "url": "https://example.com/job/1",
                    "extra": "drop-me",
                }
            ]
        ),
        "fields": ["title", "company", "url"],
    }

    result = _scrape_with(_run_result(filtered))
    site_entry = result["results"][0]["sites"][0]
    job = site_entry["jobs"][0]

    assert set(job.keys()) == set(JOB_FIELD_ORDER)
    assert job["site"] == SITE
    assert job["matched_keyword"] == KEYWORD
    assert "extra" not in job
    assert site_entry["count"] == 1


@patch("mcp_server.server.mongo")
def test_scrape_jobs_returns_mongo_id_and_builds_document(mock_mongo):
    raw = {
        "keyword": KEYWORD,
        "fields": list(JOB_FIELD_ORDER),
        "count": 5,
        "jobs": [{"title": t} for t in "ABCDE"],
    }
    mock_mongo.insert_run.return_value = "deadbeef"

    result = _scrape_with(_run_result(_filtered([{"title": "A"}, {"title": "B"}]), raw))

    assert result["mongo_id"] == "deadbeef"
    doc = mock_mongo.insert_run.call_args.args[0]
    assert doc["raw_results"][0]["payload"]["count"] == 5
    assert doc["filtered_results"][0]["payload"]["count"] == 2
    assert doc["run_metadata"]["per_site_counts"] == {SITE: {KEYWORD: 2}}
    assert "raw_results" not in doc["run_metadata"]
    assert doc["note"] is None


@patch("mcp_server.server.mongo")
def test_scrape_jobs_sets_note_on_error(mock_mongo):
    mock_mongo.insert_run.return_value = "id1"

    _scrape_with(_run_result(FETCH_FAILED))

    doc = mock_mongo.insert_run.call_args.args[0]
    assert doc["note"] is not None and SITE in doc["note"]


@patch("mcp_server.server.mongo")
def test_scrape_jobs_skips_mongo_when_save_run_is_false(mock_mongo):
    result = _scrape_with(_run_result(_filtered([{"title": "A"}])), save_run=False)

    mock_mongo.insert_run.assert_not_called()
    assert result["mongo_id"] is None
    assert result["ok"] is True
    assert result["results"][0]["sites"][0]["count"] == 1


def test_get_scrape_response_structure_exposes_canonical_fields():
    from mcp_server.server import get_scrape_response_structure

    out = get_scrape_response_structure()

    assert out["tool"] == "scrape_jobs"
    assert out["job_fields"] == list(JOB_FIELD_ORDER)
    assert out["top_level_fields"] == [
        "ok",
        "keywords",
        "requested_sites",
        "exit_code",
        "results",
        "errors",
        "mongo_id",
    ]


@patch("mcp_server.server._load_config", side_effect=SettingsMissingError("settings missing"))
def test_ok_false_when_settings_cannot_load(mock_load):
    from mcp_server.server import scrape_jobs

    result = scrape_jobs(keywords=[KEYWORD], sites=[SITE])

    assert result == {"ok": False, "error": "settings missing"}


RAW_PAYLOAD = {"keyword": KEYWORD, "count": 3, "jobs": [{"title": "A"}, {"title": "B"}]}
FILTERED_PAYLOAD = _filtered([{"title": "A"}], max_age_hours=None)


@patch("mcp_server.server.mongo")
def test_scrape_jobs_omits_payloads_by_default(mock_mongo):
    result = _scrape_with(_run_result(FILTERED_PAYLOAD, RAW_PAYLOAD))

    assert "raw_results" not in result
    assert "filtered_results" not in result


@patch("mcp_server.server.mongo")
def test_scrape_jobs_includes_raw_and_filtered_payloads_when_asked(mock_mongo):
    result = _scrape_with(_run_result(FILTERED_PAYLOAD, RAW_PAYLOAD), include_payloads=True)

    assert result["raw_results"] == [{"keyword": KEYWORD, "site": SITE, "payload": RAW_PAYLOAD}]
    assert result["filtered_results"] == [
        {"keyword": KEYWORD, "site": SITE, "payload": FILTERED_PAYLOAD}
    ]


@patch("mcp_server.server.mongo")
def test_scrape_jobs_includes_payloads_when_run_is_not_saved(mock_mongo):
    result = _scrape_with(
        _run_result(FILTERED_PAYLOAD, RAW_PAYLOAD), include_payloads=True, save_run=False
    )

    assert result["mongo_id"] is None
    assert len(result["raw_results"]) == 1
    assert len(result["filtered_results"]) == 1
