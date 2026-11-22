from __future__ import annotations

from types import MappingProxyType
from typing import Any
from unittest.mock import MagicMock, create_autospec, patch

import pytest

from scraper.config_loader import AppConfig
from scraper.job_settings import SettingsMissingError
from scraper.runner import FilteredAndRawPayloads, RunResult, build_keyword_site_pair_error_payloads
from scraper.types import JOB_FIELD_ORDER

KEYWORD = "data analyst"
SITE = "jobstreet"
EMPTY_RAW: dict[str, Any] = {"keyword": KEYWORD, "count": 0, "jobs": []}


def _make_config(site: str = SITE) -> MagicMock:
    config = create_autospec(AppConfig, instance=True)
    config.list_enabled_site_names.return_value = (site,)
    return config


def _run_result(filtered: dict[str, Any], raw: dict[str, Any] | None = None) -> RunResult:
    payloads = FilteredAndRawPayloads(filtered=filtered, raw=raw if raw is not None else EMPTY_RAW)
    return RunResult(exit_code=0, results=MappingProxyType({(KEYWORD, SITE): payloads}))


def _scrape_with(run_result: RunResult, **kwargs: Any) -> dict[str, Any]:
    from mcp_server.server import scrape_jobs

    with (
        patch("mcp_server.server._load_app_config", return_value=_make_config()),
        patch("mcp_server.server.scrape_all_sites", autospec=True, return_value=run_result),
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
    assert result["results"] == [{"keyword": KEYWORD, "site": SITE, "payload": _filtered([])}]


@patch("mcp_server.server.mongo")
def test_ok_true_when_jobs_found(mock_mongo):
    result = _scrape_with(_run_result(_filtered([{"title": "A"}, {"title": "B"}])))

    assert result["ok"] is True
    assert result["errors"] == []
    assert len(result["results"]) == 1
    assert result["results"][0]["payload"]["count"] == 2
    assert result["results"][0]["payload"]["jobs"] == [{"title": "A"}, {"title": "B"}]


@patch("mcp_server.server.mongo")
def test_ok_false_when_fetch_failed(mock_mongo):
    result = _scrape_with(_run_result(FETCH_FAILED))

    assert result["ok"] is False
    assert len(result["errors"]) == 1
    assert result["errors"][0]["reason"] == "fetch failed"
    assert (result["errors"][0]["keyword"], result["errors"][0]["site"]) == (KEYWORD, SITE)
    assert result["results"] == [{"keyword": KEYWORD, "site": SITE, "payload": FETCH_FAILED}]
    assert result["results"][0]["payload"]["error"] == "fetch failed"


@patch("mcp_server.server.mongo")
def test_fetch_failure_attempts_are_reported(mock_mongo):
    attempts = [{"downloader": "curl_cffi", "code": "http_403", "detail": None}]
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
    assert result["results"] == []


@patch("mcp_server.server.mongo")
def test_input_error_reason_is_reported_for_every_pair(mock_mongo):
    result = _scrape_with(RunResult(exit_code=1, error="unknown sites: nope"))

    assert result["ok"] is False
    assert result["errors"] == [{"keyword": KEYWORD, "site": SITE, "reason": "unknown sites: nope"}]


@patch("mcp_server.server.mongo")
def test_skipped_or_crashed_pair_is_reported_as_error(mock_mongo):
    payloads = build_keyword_site_pair_error_payloads(KEYWORD, "crashed: RuntimeError")
    run_result = RunResult(exit_code=0, results=MappingProxyType({(KEYWORD, SITE): payloads}))
    mock_mongo.insert_run.return_value = "id1"

    result = _scrape_with(run_result)

    assert result["ok"] is False
    assert result["errors"][0]["reason"] == "crashed: RuntimeError"
    assert result["results"][0]["payload"]["error"] == "crashed: RuntimeError"
    doc = mock_mongo.insert_run.call_args.args[0]
    assert doc["results"][0]["payload"]["error"] == "crashed: RuntimeError"
    assert "filtered_results" not in doc
    assert "raw_results" not in doc


@patch("mcp_server.server.mongo")
@patch("mcp_server.server._write_scrape_status_file")
def test_scrape_jobs_writes_status(mock_write_status, mock_mongo):
    _scrape_with(_run_result(_filtered([{"title": "A"}], max_age_hours=None)))

    mock_write_status.assert_called_once()
    result_arg, duration_arg = mock_write_status.call_args.args
    assert result_arg["ok"] is True
    assert isinstance(duration_arg, float)


@patch("mcp_server.server.mongo")
def test_scrape_jobs_returns_each_site_payload_unchanged(mock_mongo):
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

    assert result["results"] == [{"keyword": KEYWORD, "site": SITE, "payload": filtered}]
    assert set(result["results"][0]) == {"keyword", "site", "payload"}
    assert "sites" not in result["results"][0]
    assert "filtered_results" not in result


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
    assert set(doc) == {"run_metadata", "results", "note"}
    assert "raw_results" not in doc
    assert "filtered_results" not in doc
    assert doc["results"] == result["results"]
    assert doc["results"][0]["payload"]["count"] == 2
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
    assert result["results"][0]["payload"]["count"] == 1


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
    assert out["optional_top_level_fields"] == ["raw_results"]
    assert out["result_fields"] == ["keyword", "site", "payload"]
    assert out["error_fields"] == ["keyword", "site", "reason", "attempts"]
    assert "site_result_fields" not in out


@patch("mcp_server.server.mongo")
def test_get_scrape_response_structure_matches_the_real_response_keys(mock_mongo):
    from mcp_server.server import get_scrape_response_structure

    mock_mongo.insert_run.return_value = "deadbeef"
    structure = get_scrape_response_structure()
    sample = structure["sample"]

    result = _scrape_with(_run_result(FILTERED_PAYLOAD, RAW_PAYLOAD))
    result_with_raw = _scrape_with(
        _run_result(FILTERED_PAYLOAD, RAW_PAYLOAD), include_raw_results=True
    )

    assert list(result) == structure["top_level_fields"]
    assert list(result_with_raw) == [
        *structure["top_level_fields"],
        *structure["optional_top_level_fields"],
    ]
    assert list(sample) == structure["top_level_fields"]
    assert list(result["results"][0]) == structure["result_fields"]
    assert list(sample["results"][0]) == structure["result_fields"]
    assert list(sample["results"][0]["payload"]) == structure["payload_fields"]
    assert set(sample["results"][0]["payload"]["jobs"][0]) == set(JOB_FIELD_ORDER)


def test_get_scrape_response_structure_payload_fields_match_the_runner_payload():
    from mcp_server.server import get_scrape_response_structure
    from scraper import runner
    from tests.runner_fakes import FakeScraper, build_html_downloader_returning

    job = {"title": "A", "company": "ACME", "url": "https://x/A", "location": "Jakarta"}
    scraper = FakeScraper(name="fake", url="https://example.test/search", limit=5, jobs=[job])

    payloads = runner.scrape_site_for_keyword(
        scraper,
        build_html_downloader_returning("<html>ok</html>"),
        KEYWORD,
        frozenset({"title", "company", "url", "location"}),
        None,
        {},
    )

    assert list(payloads.filtered) == get_scrape_response_structure()["payload_fields"]


@patch("mcp_server.server._load_app_config", side_effect=SettingsMissingError("settings missing"))
def test_ok_false_when_settings_cannot_load(mock_load):
    from mcp_server.server import scrape_jobs

    result = scrape_jobs(keywords=[KEYWORD], sites=[SITE])

    assert result == {"ok": False, "error": "settings missing"}


RAW_PAYLOAD = {"keyword": KEYWORD, "count": 3, "jobs": [{"title": "A"}, {"title": "B"}]}
FILTERED_PAYLOAD = _filtered([{"title": "A"}], max_age_hours=None)


@patch("mcp_server.server.mongo")
def test_scrape_jobs_omits_raw_results_by_default(mock_mongo):
    result = _scrape_with(_run_result(FILTERED_PAYLOAD, RAW_PAYLOAD))

    assert "raw_results" not in result
    assert "filtered_results" not in result
    assert result["results"] == [{"keyword": KEYWORD, "site": SITE, "payload": FILTERED_PAYLOAD}]


@patch("mcp_server.server.mongo")
def test_scrape_jobs_omits_raw_results_when_include_raw_results_is_false(mock_mongo):
    result = _scrape_with(_run_result(FILTERED_PAYLOAD, RAW_PAYLOAD), include_raw_results=False)

    assert "raw_results" not in result


@patch("mcp_server.server.mongo")
def test_scrape_jobs_includes_raw_results_when_asked(mock_mongo):
    result = _scrape_with(_run_result(FILTERED_PAYLOAD, RAW_PAYLOAD), include_raw_results=True)

    assert result["raw_results"] == [{"keyword": KEYWORD, "site": SITE, "payload": RAW_PAYLOAD}]
    assert result["results"] == [{"keyword": KEYWORD, "site": SITE, "payload": FILTERED_PAYLOAD}]
    assert "filtered_results" not in result


@patch("mcp_server.server.mongo")
def test_scrape_jobs_returns_raw_results_but_saves_only_results(mock_mongo):
    mock_mongo.insert_run.return_value = "deadbeef"

    result = _scrape_with(_run_result(FILTERED_PAYLOAD, RAW_PAYLOAD), include_raw_results=True)

    results = [{"keyword": KEYWORD, "site": SITE, "payload": FILTERED_PAYLOAD}]
    assert result["mongo_id"] == "deadbeef"
    assert result["raw_results"] == [{"keyword": KEYWORD, "site": SITE, "payload": RAW_PAYLOAD}]
    assert result["results"] == results
    doc = mock_mongo.insert_run.call_args.args[0]
    assert "raw_results" not in doc
    assert "filtered_results" not in doc
    assert doc["results"] == results
    assert doc["run_metadata"]["keywords"] == [KEYWORD]
    assert doc["run_metadata"]["per_site_counts"] == {SITE: {KEYWORD: 1}}


@patch("mcp_server.server.mongo")
def test_scrape_jobs_includes_raw_results_when_run_is_not_saved(mock_mongo):
    result = _scrape_with(
        _run_result(FILTERED_PAYLOAD, RAW_PAYLOAD), include_raw_results=True, save_run=False
    )

    assert result["mongo_id"] is None
    assert len(result["raw_results"]) == 1
    assert len(result["results"]) == 1


def test_scrape_jobs_has_no_include_payloads_parameter():
    import inspect

    from mcp_server.server import scrape_jobs

    parameters = inspect.signature(scrape_jobs).parameters

    assert "include_payloads" not in parameters
    assert parameters["include_raw_results"].default is False


@pytest.mark.parametrize("keywords", [None, [], ["", "   "]])
@patch("mcp_server.server._write_scrape_status_file")
@patch("mcp_server.server.scrape_all_sites", autospec=True)
@patch("mcp_server.server._load_app_config")
@patch("mcp_server.server.mongo")
def test_scrape_jobs_without_keywords_is_refused_without_running_or_saving(
    mock_mongo, mock_load, mock_run, mock_write_status, keywords
):
    from mcp_server.server import scrape_jobs

    result = scrape_jobs(keywords=keywords, sites=[SITE])

    assert result == {
        "ok": False,
        "keywords": [],
        "requested_sites": [SITE],
        "exit_code": 1,
        "results": [],
        "errors": [{"keyword": None, "site": None, "reason": "keywords are required"}],
        "mongo_id": None,
    }
    mock_run.assert_not_called()
    mock_load.assert_not_called()
    mock_mongo.insert_run.assert_not_called()
    mock_write_status.assert_not_called()


def test_scrape_jobs_requires_keywords_in_its_signature():
    import inspect

    from mcp_server.server import scrape_jobs

    parameter = inspect.signature(scrape_jobs).parameters["keywords"]

    assert parameter.default is inspect.Parameter.empty
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY


def test_scrape_jobs_keeps_sites_as_the_first_positional_parameter():
    import inspect

    from mcp_server.server import scrape_jobs

    parameters = list(inspect.signature(scrape_jobs).parameters.values())

    assert parameters[0].name == "sites"
    assert parameters[0].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in parameters[1:])


def test_scrape_jobs_positional_keywords_fail_loudly():
    from mcp_server.server import scrape_jobs

    with pytest.raises(TypeError):
        scrape_jobs([SITE], [KEYWORD])


def test_scrape_jobs_tool_schema_lists_keywords_as_required():
    import asyncio

    from mcp_server.server import mcp

    tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}

    assert tools["scrape_jobs"].inputSchema["required"] == ["keywords"]


@patch("mcp_server.server._write_scrape_status_file")
@patch("mcp_server.server.mongo")
def test_scrape_jobs_strips_keywords_and_drops_blank_ones(mock_mongo, mock_write_status):
    from mcp_server.server import scrape_jobs

    run_result = _run_result(_filtered([]))
    with (
        patch("mcp_server.server._load_app_config", return_value=_make_config()),
        patch(
            "mcp_server.server.scrape_all_sites", autospec=True, return_value=run_result
        ) as mock_run,
    ):
        result = scrape_jobs([SITE], keywords=[f"  {KEYWORD} ", " "])

    assert mock_run.call_args.kwargs["keywords"] == [KEYWORD]
    assert result["keywords"] == [KEYWORD]


@patch("mcp_server.server._write_scrape_status_file")
@patch("mcp_server.server.mongo")
def test_scrape_jobs_forwards_requested_sites_to_scrape_all_sites(mock_mongo, mock_write_status):
    from mcp_server.server import scrape_jobs

    config = _make_config()
    run_result = _run_result(_filtered([]))
    with (
        patch("mcp_server.server._load_app_config", return_value=config),
        patch(
            "mcp_server.server.scrape_all_sites", autospec=True, return_value=run_result
        ) as mock_scrape_all_sites,
    ):
        scrape_jobs([SITE, "glints"], keywords=[KEYWORD])

    mock_scrape_all_sites.assert_called_once_with(
        config,
        requested_sites=[SITE, "glints"],
        keywords=[KEYWORD],
        requested_location=None,
        requested_max_age_hours=None,
    )


@patch("mcp_server.server._write_scrape_status_file")
@patch("mcp_server.server.mongo")
def test_scrape_jobs_without_sites_forwards_the_enabled_sites_from_config(
    mock_mongo, mock_write_status
):
    from mcp_server.server import scrape_jobs

    config = _make_config(site="linkedin")
    run_result = _run_result(_filtered([]))
    with (
        patch("mcp_server.server._load_app_config", return_value=config),
        patch(
            "mcp_server.server.scrape_all_sites", autospec=True, return_value=run_result
        ) as mock_scrape_all_sites,
    ):
        scrape_jobs(keywords=[KEYWORD])

    assert mock_scrape_all_sites.call_args.kwargs["requested_sites"] == ["linkedin"]
