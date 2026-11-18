from __future__ import annotations

import operator
from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from scraper import runner
from scraper.config_loader import parse

SETTINGS: dict[str, Any] = {
    "keywords": ["devops", "qa"],
    "concurrency": 1,
    "sites": {
        "jobstreet": {"url_template": "https://id.jobstreet.com/id/{keyword_slug}-jobs"},
        "glints": {
            "url_template": "https://glints.com/id/opportunities/jobs/explore?keyword={keyword}"
        },
    },
}


def _ok(keyword: str) -> runner.SitePayloads:
    return runner.SitePayloads(
        filtered={"keyword": keyword, "count": 0, "jobs": []},
        raw={"keyword": keyword, "count": 0, "jobs": []},
    )


@pytest.fixture(autouse=True)
def _no_mongo_index(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "refresh_index", lambda: None)


@pytest.mark.parametrize("concurrency", [1, 4])
def test_run_returns_payloads_keyed_by_keyword_and_site(
    monkeypatch: pytest.MonkeyPatch, concurrency: int
):
    def fake_run_one(scraper: Any, fetcher: Any, keyword: str, *args: Any, **kwargs: Any):
        return _ok(keyword)

    monkeypatch.setattr(runner, "run_one", fake_run_one)

    result = runner.run(parse({**SETTINGS, "concurrency": concurrency}, None))

    assert result.exit_code == 0
    assert list(result.results) == [
        ("devops", "jobstreet"),
        ("devops", "glints"),
        ("qa", "jobstreet"),
        ("qa", "glints"),
    ]
    assert result.get("qa", "glints") == _ok("qa")


@pytest.mark.parametrize("concurrency", [1, 4])
def test_crashed_pair_is_reported_as_error_and_others_still_run(
    monkeypatch: pytest.MonkeyPatch, concurrency: int
):
    def fake_run_one(scraper: Any, fetcher: Any, keyword: str, *args: Any, **kwargs: Any):
        if scraper.name == "glints" and keyword == "qa":
            raise RuntimeError("secret proxy detail")
        return _ok(keyword)

    monkeypatch.setattr(runner, "run_one", fake_run_one)

    result = runner.run(parse({**SETTINGS, "concurrency": concurrency}, None))

    crashed = result.get("qa", "glints")
    assert crashed is not None
    assert crashed.filtered == {
        "error": "crashed: RuntimeError",
        "keyword": "qa",
        "source": None,
        "fallback_reason": None,
    }
    assert crashed.raw == {
        "keyword": "qa",
        "count": 0,
        "jobs": [],
        "error": "crashed: RuntimeError",
    }
    assert "secret" not in str(crashed)
    assert result.get("devops", "glints") == _ok("devops")


def test_site_without_settings_entry_is_reported_as_skipped(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(runner, "run_one", lambda *a, **k: _ok("devops"))

    result = runner.run(parse(SETTINGS, None), targets=["linkedin"], keywords=["devops"])

    skipped = result.get("devops", "linkedin")
    assert result.exit_code == 0
    assert skipped is not None
    assert skipped.filtered["error"] == "skipped: site has no entry in the job settings"
    assert skipped.raw["jobs"] == []


def _all_disabled() -> dict[str, Any]:
    sites = {name: {**cfg, "enabled": False} for name, cfg in SETTINGS["sites"].items()}
    return {**SETTINGS, "sites": sites}


@pytest.mark.parametrize(
    ("settings", "targets"),
    [(SETTINGS, ["nope"]), (_all_disabled(), [])],
)
def test_invalid_selection_returns_exit_code_one_and_no_results(
    settings: dict[str, Any], targets: list[str], monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(runner, "run_one", lambda *a, **k: pytest.fail("must not run"))

    result = runner.run(parse(settings, None), targets=targets)

    assert result.exit_code == 1
    assert dict(result.results) == {}
    assert result.error is not None


def test_run_result_is_immutable():
    result = runner.RunResult(exit_code=0)

    with pytest.raises(FrozenInstanceError):
        result.__setattr__("exit_code", 1)
    with pytest.raises(TypeError):
        operator.setitem(result.results, ("a", "b"), _ok("a"))
