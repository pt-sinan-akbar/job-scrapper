from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from types import MappingProxyType
from typing import Any

import mongomock
import pytest

from scraper import __main__ as cli
from scraper.config_loader import PROXY_ENV_VAR
from scraper.job_settings import JobSettingsStore
from scraper.runner import RunResult, SitePayloads

SETTINGS: dict[str, Any] = {
    "sites": {
        "upwork": {
            "limit": 3,
            "url_template": "https://www.upwork.com/nx/search/jobs/?q={keyword}&sort=recency",
        }
    },
}


def test_cli_runs_with_settings_from_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    store = JobSettingsStore(mongomock.MongoClient()["job_scraper"])
    store.seed(deepcopy(SETTINGS))
    calls: list[tuple[Any, Any, Any]] = []
    monkeypatch.setenv(PROXY_ENV_VAR, "")
    monkeypatch.setattr(cli, "open_store", lambda: store)

    def fake_run(config: Any, targets: Any, keywords: Any) -> RunResult:
        calls.append((config, targets, keywords))
        return RunResult(exit_code=0)

    monkeypatch.setattr(cli, "run", fake_run)

    code = cli.main(["-k", "python", "upwork"])

    assert code == 0
    assert calls[0][0].site("upwork") is not None
    assert calls[0][1] == ["upwork"]
    assert calls[0][2] == ["python"]


def test_cli_without_keyword_exits_2_and_runs_nothing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setenv(PROXY_ENV_VAR, "")
    monkeypatch.setattr(cli, "open_store", _store_with_settings)
    monkeypatch.setattr(cli, "run", lambda *a, **k: pytest.fail("must not run"))

    code = cli.main(["upwork"])

    captured = capsys.readouterr()
    assert code == 2
    assert "keywords are required" in captured.err
    assert captured.out == ""


def test_cli_without_keyword_does_not_need_the_store(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setattr(cli, "open_store", lambda: pytest.fail("must not open the store"))

    assert cli.main([]) == 2
    assert "keywords are required" in capsys.readouterr().err


def test_cli_reports_missing_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    store = JobSettingsStore(mongomock.MongoClient()["job_scraper"])
    monkeypatch.setenv(PROXY_ENV_VAR, "")
    monkeypatch.setattr(cli, "open_store", lambda: store)

    assert cli.main(["-k", "python"]) == 2
    assert "seed.sh" in capsys.readouterr().err


def _store_with_settings() -> JobSettingsStore:
    store = JobSettingsStore(mongomock.MongoClient()["job_scraper"])
    store.seed(deepcopy(SETTINGS))
    return store


@pytest.mark.parametrize("exit_code", [0, 1])
def test_cli_prints_filtered_results_json_to_stdout(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], exit_code: int
):
    filtered = {"keyword": "devops", "count": 1, "jobs": [{"title": "Engineer"}]}
    payloads = SitePayloads(filtered=filtered, raw={"keyword": "devops", "count": 9, "jobs": []})
    run_result = RunResult(
        exit_code=exit_code, results=MappingProxyType({("devops", "upwork"): payloads})
    )
    monkeypatch.setenv(PROXY_ENV_VAR, "")
    monkeypatch.setattr(cli, "open_store", _store_with_settings)
    monkeypatch.setattr(cli, "run", lambda config, targets, keywords: run_result)

    code = cli.main(["-k", "devops"])

    assert code == exit_code
    assert json.loads(capsys.readouterr().out) == [
        {"keyword": "devops", "site": "upwork", "payload": filtered}
    ]


def test_cli_escapes_non_ascii_so_any_locale_can_print_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    filtered = {"keyword": "devops", "count": 1, "jobs": [{"title": "Insinyur Café"}]}
    payloads = SitePayloads(filtered=filtered, raw=None)
    run_result = RunResult(exit_code=0, results=MappingProxyType({("devops", "upwork"): payloads}))
    monkeypatch.setenv(PROXY_ENV_VAR, "")
    monkeypatch.setattr(cli, "open_store", _store_with_settings)
    monkeypatch.setattr(cli, "run", lambda config, targets, keywords: run_result)

    cli.main(["-k", "devops"])

    out = capsys.readouterr().out
    assert out.isascii()
    assert json.loads(out)[0]["payload"]["jobs"][0]["title"] == "Insinyur Café"


@pytest.mark.parametrize("argv", [["-k", "  "], ["-k", "", "-k", " ", "upwork"]])
def test_cli_with_only_blank_keywords_exits_2_and_runs_nothing(
    argv: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setattr(cli, "open_store", lambda: pytest.fail("must not open the store"))
    monkeypatch.setattr(cli, "run", lambda *a, **k: pytest.fail("must not run"))

    assert cli.main(argv) == 2
    assert "keywords are required" in capsys.readouterr().err


def test_cli_strips_keywords_and_drops_blank_ones(monkeypatch: pytest.MonkeyPatch):
    calls: list[Any] = []
    monkeypatch.setenv(PROXY_ENV_VAR, "")
    monkeypatch.setattr(cli, "open_store", _store_with_settings)

    def fake_run(config: Any, targets: Any, keywords: Any) -> RunResult:
        calls.append(keywords)
        return RunResult(exit_code=0)

    monkeypatch.setattr(cli, "run", fake_run)

    assert cli.main(["-k", " python ", "-k", "  "]) == 0
    assert calls == [["python"]]
