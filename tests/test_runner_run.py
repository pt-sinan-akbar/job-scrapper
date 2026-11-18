from __future__ import annotations

import operator
from dataclasses import FrozenInstanceError
from typing import Any

import pytest

from scraper import runner
from scraper.config_loader import CONCURRENCY_ENV_VAR, parse

KEYWORDS = ["devops", "qa"]
SETTINGS: dict[str, Any] = {
    "sites": {
        "jobstreet": {
            "limit": 3,
            "url_template": "https://id.jobstreet.com/id/{keyword_slug}-jobs",
        },
        "glints": {
            "limit": 3,
            "url_template": "https://glints.com/id/opportunities/jobs/explore?keyword={keyword}",
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
    monkeypatch.setenv(CONCURRENCY_ENV_VAR, str(concurrency))

    result = runner.run(parse(SETTINGS, None), keywords=KEYWORDS)

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
    monkeypatch.setenv(CONCURRENCY_ENV_VAR, str(concurrency))

    result = runner.run(parse(SETTINGS, None), keywords=KEYWORDS)

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


@pytest.mark.parametrize(("raw", "workers"), [("3", 3), ("10", 4), ("abc", 2), (None, 2)])
def test_run_uses_scraper_concurrency_env(
    monkeypatch: pytest.MonkeyPatch, raw: str | None, workers: int
):
    seen: list[int] = []
    real_executor = runner.ThreadPoolExecutor

    def recording_executor(max_workers: int, **kwargs: Any) -> Any:
        seen.append(max_workers)
        return real_executor(max_workers=max_workers, **kwargs)

    if raw is None:
        monkeypatch.delenv(CONCURRENCY_ENV_VAR, raising=False)
    else:
        monkeypatch.setenv(CONCURRENCY_ENV_VAR, raw)
    monkeypatch.setattr(runner, "ThreadPoolExecutor", recording_executor)
    monkeypatch.setattr(runner, "run_one", lambda scraper, fetcher, keyword, *a, **k: _ok(keyword))

    assert runner.run(parse(SETTINGS, None), keywords=KEYWORDS).exit_code == 0
    assert seen == [workers]


def test_run_gives_each_site_its_own_limit_age_and_filter(monkeypatch: pytest.MonkeyPatch):
    received: dict[str, tuple[int, Any, Any]] = {}

    def fake_run_one(scraper: Any, fetcher: Any, keyword: str, fields: Any, *args: Any, **k: Any):
        received[scraper.name] = (scraper.limit, *args)
        return _ok(keyword)

    sites = {
        "jobstreet": {**SETTINGS["sites"]["jobstreet"], "limit": 7, "max_age_hours": 24},
        "glints": {**SETTINGS["sites"]["glints"], "filter": {"location": ["bandung"]}},
    }
    monkeypatch.setattr(runner, "run_one", fake_run_one)

    runner.run(parse({**SETTINGS, "sites": sites}, None), keywords=["devops"])

    assert received == {
        "jobstreet": (7, 24, {}),
        "glints": (3, None, {"location": ["bandung"]}),
    }


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

    result = runner.run(parse(settings, None), targets=targets, keywords=KEYWORDS)

    assert result.exit_code == 1
    assert dict(result.results) == {}
    assert result.error is not None


@pytest.mark.parametrize("keywords", [None, [], ["", "   "], ["\t\n"]])
def test_run_without_keywords_is_refused_and_runs_nothing(
    keywords: list[str] | None, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(runner, "run_one", lambda *a, **k: pytest.fail("must not run"))

    result = runner.run(parse(SETTINGS, None), keywords=keywords)

    assert result.exit_code == 1
    assert dict(result.results) == {}
    assert result.error == "keywords are required"


def test_run_without_keywords_argument_is_refused(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(runner, "run_one", lambda *a, **k: pytest.fail("must not run"))

    result = runner.run(parse(SETTINGS, None), targets=["jobstreet"])

    assert result.exit_code == 1
    assert result.error == "keywords are required"


def test_run_strips_keywords_and_drops_blank_ones(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(runner, "run_one", lambda s, f, keyword, *a, **k: _ok(keyword))

    result = runner.run(parse(SETTINGS, None), targets=["glints"], keywords=["  devops ", " ", ""])

    assert list(result.results) == [("devops", "glints")]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, []),
        ([], []),
        (["  ", ""], []),
        ([" data analyst ", "qa", "\t"], ["data analyst", "qa"]),
        (("devops",), ["devops"]),
    ],
)
def test_normalize_keywords(raw: Any, expected: list[str]):
    assert runner.normalize_keywords(raw) == expected


def test_run_result_is_immutable():
    result = runner.RunResult(exit_code=0)

    with pytest.raises(FrozenInstanceError):
        result.__setattr__("exit_code", 1)
    with pytest.raises(TypeError):
        operator.setitem(result.results, ("a", "b"), _ok("a"))
