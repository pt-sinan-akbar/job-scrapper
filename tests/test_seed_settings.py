from __future__ import annotations

from pathlib import Path

import mongomock
import pytest
import yaml

from scraper import seed_settings
from scraper.config_loader import validate_job_settings
from scraper.job_settings import JobSettingsStore

REPO_ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = REPO_ROOT / "seeds" / "job_settings.yaml"
CITIES = ["Jakarta", "Tangerang", "Tangerang Selatan", "Bandung", "Bekasi", "Indonesia"]
SMALL_SEED = """
sites:
  upwork:
    limit: 3
    url_template: "https://www.upwork.com/nx/search/jobs/?q={keyword}&sort=recency"
"""


def _store() -> JobSettingsStore:
    return JobSettingsStore(mongomock.MongoClient()["job_scraper"])


def test_committed_seed_file_is_valid():
    validate_job_settings(yaml.safe_load(SEED_PATH.read_text()))


def test_committed_seed_file_keeps_upwork_location_filter_off():
    settings = yaml.safe_load(SEED_PATH.read_text())

    assert settings["sites"]["upwork"]["filter"] == {}


def test_committed_seed_file_has_no_global_job_values():
    settings = yaml.safe_load(SEED_PATH.read_text())

    assert set(settings) == {"fields", "sites"}


def test_committed_seed_file_gives_each_site_its_old_values():
    sites = yaml.safe_load(SEED_PATH.read_text())["sites"]
    city_sites = ["jobstreet", "glints", "linkedin", "indeed"]

    assert {name: site["limit"] for name, site in sites.items()} == {
        **dict.fromkeys(city_sites, 3),
        "upwork": 30,
    }
    assert all(site["max_age_hours"] == 72 for site in sites.values())
    assert all(sites[name]["filter"] == {"location": CITIES} for name in city_sites)


def test_seed_file_inserts_once(tmp_path: Path):
    path = tmp_path / "seed.yaml"
    path.write_text(SMALL_SEED)
    store = _store()

    assert seed_settings.seed_file(path, store) is True
    assert seed_settings.seed_file(path, store) is False


def test_main_returns_zero_when_seeded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    path = tmp_path / "seed.yaml"
    path.write_text(SMALL_SEED)
    monkeypatch.setattr(seed_settings, "open_store", _store)

    assert seed_settings.main(["--file", str(path)]) == 0
    assert "inserted" in capsys.readouterr().out


def test_main_reports_invalid_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    path = tmp_path / "seed.yaml"
    path.write_text("keywords: [devops]\n")
    monkeypatch.setattr(seed_settings, "open_store", _store)

    assert seed_settings.main(["--file", str(path)]) == 2
    assert "not a job setting: keywords" in capsys.readouterr().err


def test_committed_seed_file_has_no_site_fields():
    sites = yaml.safe_load(SEED_PATH.read_text())["sites"]

    for site in sites.values():
        assert "fields" not in site


def test_committed_seed_file_has_no_api_locations_or_country_wide():
    sites = yaml.safe_load(SEED_PATH.read_text())["sites"]

    for site in sites.values():
        api_settings = site.get("api", {})
        assert "locations" not in api_settings
        assert "country_wide" not in api_settings


def test_committed_seed_file_keeps_the_api_switch_and_the_linkedin_delay():
    sites = yaml.safe_load(SEED_PATH.read_text())["sites"]

    assert sites["jobstreet"]["api"] == {"enabled": True}
    assert sites["glints"]["api"] == {"enabled": True}
    assert sites["linkedin"]["api"] == {"enabled": True, "delay_seconds": [4, 6]}
    assert sites["upwork"]["api"] == {"enabled": True}
    assert "api" not in sites["indeed"]
