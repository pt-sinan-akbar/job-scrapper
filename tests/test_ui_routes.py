from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import mongomock
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.errors import McpUnavailableError
from backend.services.scrape_report_repository import (
    SCRAPE_REPORTS_COLLECTION,
    MongoScrapeReportRepository,
    ScrapeStoreUnavailableError,
)
from backend.settings import Settings

PASSWORD = "correct horse battery"  # pragma: allowlist secret
AUTH_TOKEN = "auth-token-for-tests-1234"
LOCAL_URL = "http://127.0.0.1:8090"
SITES = {
    "sites": [{"name": "upwork", "enabled": True, "url_template": "x", "sample_url": "x"}],
}
CONFIG = {
    "version": 4,
    "updated_at": "2026-11-02T01:00:00+00:00",
    "updated_by": "ui",
    "settings": {
        "fields": ["title"],
        "sites": {
            "upwork": {
                "enabled": True,
                "limit": 30,
                "filter": {},
                "url_template": "x",
                "api": {"locations": ["Remote"]},
            },
            "indeed": {
                "limit": 3,
                "max_age_hours": 72,
                "filter": {"location": "jakarta", "work_type": []},
                "url_template": "x",
            },
        },
    },
    "job_fields": ["site", "title", "salary_min"],
    "mandatory_fields": ["site", "title"],
    "location_options": {"jobstreet": [{"label": "Jakarta", "value": "Jakarta Raya"}]},
}
SAVED = {"ok": True, "version": 5}
SITE_LIMIT = {"upwork": {"limit": 9}}
DISCORD_SETTINGS = {
    "configured": True,
    "default_channel_id": "123456789012345678",
    "mention_user_id": "",
}
SCRAPE_RESULT = {
    "ok": True,
    "results": [{"keyword": "devops", "site": "upwork", "payload": {"jobs": [{"title": "A"}]}}],
    "errors": [],
}
STORED_SCRAPE: dict[str, Any] = {
    "_id": "20261118T010000Z-abcdef",
    "saved_at": "2026-11-18T01:01:00+00:00",
    "record": {
        "id": "20261118T010000Z-abcdef",
        "status": "succeeded",
        "keywords": ["django"],
        "sites": ["upwork"],
        "started_at": "2026-11-18T01:00:00+00:00",
        "finished_at": "2026-11-18T01:01:00+00:00",
        "job_count": 1,
        "error_count": 0,
        "error": None,
        "discord_status": "sent",
        "discord_sent": 1,
        "discord_failed": 0,
        "discord_error": None,
    },
    "jobs": [
        {
            "site": "upwork",
            "matched_keyword": "django",
            "title": "Stored",
            "company": "Acme",
            "location": None,
            "url": "https://example.com/1",
            "posted_at": None,
        }
    ],
    "failures": [],
    "payloads": [{"keyword": "django", "site": "upwork", "raw": {"a": 1}, "filtered": None}],
}


class FakeGateway:
    def __init__(self) -> None:
        self.is_down = False
        self.config = CONFIG
        self.save_result: dict[str, Any] = SAVED
        self.scrape_delay = 0.0
        self.scrape_result: dict[str, Any] = SCRAPE_RESULT
        self.discord_settings: dict[str, Any] = DISCORD_SETTINGS
        self.calls: list[str] = []
        self.arguments: dict[str, dict[str, Any]] = {}

    async def call(
        self, tool: str, arguments: dict[str, Any], timeout_seconds: float
    ) -> dict[str, Any]:
        self.calls.append(tool)
        self.arguments = {**self.arguments, tool: arguments}
        if self.is_down:
            raise McpUnavailableError()
        if tool == "scrape_jobs":
            await asyncio.sleep(self.scrape_delay)
        responses: dict[str, dict[str, Any]] = {
            "list_sites": SITES,
            "get_config": self.config,
            "scrape_jobs": self.scrape_result,
            "update_config": self.save_result,
            "get_discord_settings": self.discord_settings,
            "send_discord_message": {
                "ok": True,
                "sent": 1,
                "failed": 0,
                "results": [{"kind": "file", "job_count": 1, "status": "sent"}],
            },
        }
        return responses[tool]


def _settings(tmp_path: Path, **overrides: Any) -> Settings:
    values = {
        "env": "dev",
        "auth_token": AUTH_TOKEN,
        "static_dir": tmp_path / "dist",
    }
    return Settings(**{**values, **overrides})


def _prod_settings(tmp_path: Path, **overrides: Any) -> Settings:
    values = {
        "env": "prod",
        "domain": "testserver",
        "auth_token": PASSWORD,
    }
    return _settings(tmp_path, **{**values, **overrides})


@pytest.fixture
def gateway() -> FakeGateway:
    return FakeGateway()


@pytest.fixture
def database() -> Any:
    return mongomock.MongoClient()["job_scraper"]


@pytest.fixture
def guest_client(tmp_path: Path, gateway: FakeGateway, database: Any):
    app = create_app(_settings(tmp_path), gateway, MongoScrapeReportRepository(database))
    with TestClient(app, base_url=LOCAL_URL) as test_client:
        yield test_client


@pytest.fixture
def client(guest_client: TestClient):
    guest_client.post("/api/auth/login", json={"password": AUTH_TOKEN})
    return guest_client


@pytest.fixture
def prod_client(tmp_path: Path, gateway: FakeGateway, database: Any):
    app = create_app(_prod_settings(tmp_path), gateway, MongoScrapeReportRepository(database))
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client


def _scrape(client: TestClient) -> dict:
    response = client.post("/api/scrapes", json={"keywords": ["devops"], "sites": ["upwork"]})
    assert response.status_code == 202
    return response.json()["data"]


def test_unknown_host_is_refused(client: TestClient):
    response = client.get("/api/sites", headers={"host": "evil.example.com"})

    assert response.status_code == 400


def test_unknown_host_is_refused_in_prod(prod_client: TestClient):
    response = prod_client.get("/api/sites", headers={"host": "evil.example.com"})

    assert response.status_code == 400


def test_health_check_host_is_allowed_in_prod(prod_client: TestClient):
    assert prod_client.get("/health", headers={"host": "localhost:8090"}).status_code == 200


def test_health_needs_no_login(prod_client: TestClient):
    assert prod_client.get("/health").json() == {"status": "ok"}


def test_dev_session_needs_login(guest_client: TestClient):
    assert guest_client.get("/api/auth/session").json()["data"] == {
        "auth_required": True,
        "signed_in": False,
    }
    assert guest_client.get("/api/sites").status_code == 401


def test_bearer_auth_token_opens_api_without_login(guest_client: TestClient):
    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}

    assert guest_client.get("/api/sites", headers=headers).status_code == 200
    response = guest_client.post(
        "/api/scrapes", json={"keywords": ["devops"], "sites": ["upwork"]}, headers=headers
    )
    assert response.status_code == 202


@pytest.mark.parametrize(
    "authorization",
    ["Bearer wrong-token-value-123", AUTH_TOKEN, f"Basic {AUTH_TOKEN}", "Bearer "],
)
def test_wrong_bearer_header_returns_401(guest_client: TestClient, authorization: str):
    response = guest_client.get("/api/sites", headers={"Authorization": authorization})

    assert response.status_code == 401


def test_bearer_auth_token_opens_api_in_prod(tmp_path: Path, gateway: FakeGateway, database: Any):
    settings = _prod_settings(tmp_path, auth_token=AUTH_TOKEN)
    app = create_app(settings, gateway, MongoScrapeReportRepository(database))
    with TestClient(app, base_url="https://testserver") as prod_client:
        response = prod_client.get("/api/sites", headers={"Authorization": f"Bearer {AUTH_TOKEN}"})

    assert response.status_code == 200


def test_prod_refuses_an_empty_bearer(prod_client: TestClient):
    response = prod_client.get("/api/sites", headers={"Authorization": "Bearer "})

    assert response.status_code == 401


def test_auth_token_login_opens_api(guest_client: TestClient):
    response = guest_client.post("/api/auth/login", json={"password": AUTH_TOKEN})

    assert response.status_code == 200
    assert guest_client.get("/api/auth/session").json()["data"] == {
        "auth_required": True,
        "signed_in": True,
    }
    assert guest_client.get("/api/sites").status_code == 200


def test_dev_wrong_login_key_returns_401(guest_client: TestClient):
    response = guest_client.post("/api/auth/login", json={"password": "wrong"})

    assert response.status_code == 401
    assert guest_client.get("/api/sites").status_code == 401


def test_sites_returns_options(client: TestClient):
    data = client.get("/api/sites").json()["data"]

    assert set(data) == {"sites", "is_stale"}
    assert data["sites"] == [{"name": "upwork", "enabled": True}]
    assert data["is_stale"] is False


def test_sites_returns_503_when_mcp_is_down(client: TestClient, gateway: FakeGateway):
    gateway.is_down = True

    response = client.get("/api/sites")

    assert response.status_code == 503
    assert response.json()["success"] is False


SUMMARY_FIELDS = {
    "id",
    "status",
    "keywords",
    "sites",
    "started_at",
    "finished_at",
    "job_count",
    "error_count",
    "error",
    "discord_status",
    "discord_sent",
    "discord_failed",
    "discord_error",
}


REPORT_FIELDS = {"record", "jobs", "failures"}
JOB_FIELDS = {"site", "matched_keyword", "title", "company", "location", "url", "posted_at"}


def _read_scrape_report(client: TestClient, scrape_id: str) -> dict:
    return client.get(f"/api/scrapes/{scrape_id}").json()["data"]


def _read_scrape_summary(client: TestClient, scrape_id: str) -> dict:
    return _read_scrape_report(client, scrape_id)["record"]


def _wait_for(client: TestClient, scrape_id: str, is_pending: Any) -> dict:
    deadline = time.monotonic() + 2
    scrape_summary = _read_scrape_summary(client, scrape_id)
    while is_pending(scrape_summary) and time.monotonic() < deadline:
        time.sleep(0.01)
        scrape_summary = _read_scrape_summary(client, scrape_id)
    return scrape_summary


def _wait_for_finish(client: TestClient, scrape_id: str) -> dict:
    return _wait_for(
        client, scrape_id, lambda scrape_summary: scrape_summary["status"] == "running"
    )


def _wait_for_discord(client: TestClient, scrape_id: str) -> dict:
    return _wait_for(
        client, scrape_id, lambda scrape_summary: scrape_summary["discord_status"] == "sending"
    )


def test_start_scrape_then_read_record(client: TestClient):
    scrape = _scrape(client)

    scrape_summary = _wait_for_finish(client, scrape["id"])

    assert set(scrape_summary) == SUMMARY_FIELDS
    assert scrape_summary["id"] == scrape["id"]
    assert scrape_summary["status"] == "succeeded"
    assert scrape_summary["job_count"] == 1
    assert scrape_summary["keywords"] == ["devops"]
    assert scrape_summary["sites"] == ["upwork"]
    assert scrape_summary["finished_at"] is not None


def test_read_scrape_keeps_record_after_finish(client: TestClient):
    scrape = _scrape(client)
    _wait_for_finish(client, scrape["id"])

    response = client.get(f"/api/scrapes/{scrape['id']}")

    assert response.status_code == 200
    assert response.json()["data"]["record"]["status"] == "succeeded"


def test_new_scrape_replaces_previous_record(client: TestClient):
    first = _scrape(client)
    _wait_for_finish(client, first["id"])
    second = _scrape(client)

    assert _wait_for_finish(client, second["id"])["id"] == second["id"]
    assert client.get(f"/api/scrapes/{first['id']}").status_code == 404


def test_read_scrape_reports_failed_scrape(client: TestClient, gateway: FakeGateway):
    gateway.scrape_result = {"ok": False, "results": [], "errors": [{"site": "upwork"}]}
    scrape = _scrape(client)

    scrape_summary = _wait_for_finish(client, scrape["id"])

    assert scrape_summary["status"] == "failed"
    assert scrape_summary["error_count"] == 1


def test_scrape_asks_for_results_without_saving_the_scrape(
    client: TestClient, gateway: FakeGateway
):
    scrape = _scrape(client)
    _wait_for_finish(client, scrape["id"])

    assert gateway.arguments["scrape_jobs"] == {
        "sites": ["upwork"],
        "keywords": ["devops"],
        "save_run": False,
    }


def test_start_scrape_without_notify_has_no_discord_status(
    client: TestClient, gateway: FakeGateway
):
    scrape = _scrape(client)

    scrape_summary = _wait_for_finish(client, scrape["id"])

    assert scrape_summary["discord_status"] is None
    assert "send_discord_message" not in gateway.calls


def test_start_scrape_with_notify_sends_to_discord(client: TestClient, gateway: FakeGateway):
    response = client.post(
        "/api/scrapes",
        json={"keywords": ["devops"], "sites": ["upwork"], "notify_discord": True},
    )
    assert response.status_code == 202

    scrape_id = response.json()["data"]["id"]
    _wait_for_finish(client, scrape_id)
    scrape_summary = _wait_for_discord(client, scrape_id)

    assert scrape_summary["status"] == "succeeded"
    assert scrape_summary["discord_status"] == "sent"
    assert (scrape_summary["discord_sent"], scrape_summary["discord_failed"]) == (1, 0)
    assert gateway.arguments["send_discord_message"] == {
        "channel_id": "123456789012345678",
        "mention": False,
        "jobs": [
            {
                "site": "upwork",
                "matched_keyword": "devops",
                "title": "A",
                "company": None,
                "location": None,
                "url": None,
                "posted_at": None,
            }
        ],
        "keyword_count": 1,
        "site_count": 1,
        "error_count": 0,
    }


def test_start_scrape_rejects_non_boolean_notify(client: TestClient):
    response = client.post(
        "/api/scrapes",
        json={"keywords": ["devops"], "sites": ["upwork"], "notify_discord": "maybe"},
    )

    assert response.status_code == 422


def test_scrape_list_endpoint_is_gone(client: TestClient):
    assert client.get("/api/scrapes").status_code in (404, 405)


def test_log_stream_endpoint_is_gone(client: TestClient):
    assert client.get("/api/logs/stream").status_code == 404


def test_second_scrape_is_refused_before_reading_sites(client: TestClient, gateway: FakeGateway):
    gateway.scrape_delay = 0.2
    scrape = _scrape(client)
    gateway.calls.clear()

    response = client.post("/api/scrapes", json={"keywords": ["devops"], "sites": ["upwork"]})

    assert response.status_code == 409
    assert "list_sites" not in gateway.calls
    _wait_for_finish(client, scrape["id"])


def test_start_scrape_rejects_unknown_site(client: TestClient):
    response = client.post("/api/scrapes", json={"keywords": ["devops"], "sites": ["ghost"]})

    assert response.status_code == 422


def test_start_scrape_needs_keywords(client: TestClient):
    response = client.post("/api/scrapes", json={"keywords": [], "sites": ["upwork"]})

    assert response.status_code == 422


def test_unknown_scrape_returns_404(client: TestClient):
    assert client.get("/api/scrapes/nope").status_code == 404


class _UnavailableRepository(MongoScrapeReportRepository):
    def find(self, scrape_id: str) -> Any:
        raise ScrapeStoreUnavailableError("down")


def test_unknown_scrape_returns_503_when_scrape_storage_is_down(
    tmp_path: Path, gateway: FakeGateway, database: Any
):
    app = create_app(_settings(tmp_path), gateway, _UnavailableRepository(database))
    with TestClient(app, base_url=LOCAL_URL) as test_client:
        test_client.post("/api/auth/login", json={"password": AUTH_TOKEN})
        response = test_client.get("/api/scrapes/nope")
        latest = test_client.get("/api/scrapes/latest")

    assert response.status_code == 503
    assert response.json()["error"] == "Run storage is unavailable."
    assert latest.status_code == 200
    assert latest.json()["data"] is None


def test_app_without_a_repository_uses_the_short_timeout_scrape_store(
    tmp_path: Path, gateway: FakeGateway, monkeypatch: pytest.MonkeyPatch
):
    from backend import app as app_module

    opened: list[bool] = []

    def fake_open() -> MongoScrapeReportRepository:
        opened.append(True)
        return MongoScrapeReportRepository(mongomock.MongoClient()["job_scraper"])

    monkeypatch.setattr(app_module, "open_scrape_report_repository", fake_open)

    create_app(_settings(tmp_path), gateway)

    assert opened == [True]


def test_config_read_returns_values_and_version(client: TestClient):
    data = client.get("/api/config").json()["data"]

    assert data["version"] == 4
    assert data["updated_by"] == "ui"
    assert data["is_stale"] is False
    assert set(data["values"]) == {"fields", "sites"}
    assert data["values"]["fields"] == ["title"]
    assert "proxy_url" not in data["values"]


@pytest.mark.parametrize("key", ["limit", "concurrency", "max_age_hours", "filter"])
def test_config_update_refuses_global_job_values(
    client: TestClient, gateway: FakeGateway, key: str
):
    response = client.put("/api/config", json={"version": 4, key: 3})

    assert response.status_code == 422
    assert "update_config" not in gateway.calls


@pytest.mark.parametrize("key", ["limit", "filter"])
def test_config_update_refuses_a_null_site_limit_or_filter(
    client: TestClient, gateway: FakeGateway, key: str
):
    response = client.put("/api/config", json={"version": 4, "sites": {"upwork": {key: None}}})

    assert response.status_code == 422
    assert "update_config" not in gateway.calls


@pytest.mark.parametrize("value", [0, 201, 2.5])
def test_config_update_refuses_a_site_limit_out_of_range(client: TestClient, value: float):
    body = {"version": 4, "sites": {"upwork": {"limit": value}}}

    assert client.put("/api/config", json=body).status_code == 422


def test_config_update_sends_an_empty_site_filter(client: TestClient, gateway: FakeGateway):
    body = {"version": 4, "sites": {"upwork": {"filter": {}}}}

    assert client.put("/api/config", json=body).status_code == 200
    assert gateway.arguments["update_config"]["patch"] == {"sites": {"upwork": {"filter": {}}}}


def test_config_read_lists_job_fields_and_the_always_saved_ones(client: TestClient):
    data = client.get("/api/config").json()["data"]

    assert data["job_fields"] == ["site", "title", "salary_min"]
    assert data["mandatory_fields"] == ["site", "title"]


def test_config_read_passes_city_options_through(client: TestClient):
    data = client.get("/api/config").json()["data"]

    assert data["location_options"] == {
        "jobstreet": [{"label": "Jakarta", "value": "Jakarta Raya"}]
    }


def test_config_read_defaults_city_options_to_empty_for_an_older_scraper(
    client: TestClient, gateway: FakeGateway
):
    gateway.config = {k: v for k, v in CONFIG.items() if k != "location_options"}

    assert client.get("/api/config").json()["data"]["location_options"] == {}


def test_config_read_keeps_site_filter_states_apart(client: TestClient):
    sites = client.get("/api/config").json()["data"]["values"]["sites"]

    assert sites[0] == {
        "name": "upwork",
        "enabled": True,
        "limit": 30,
        "max_age_hours": None,
        "filter": {},
        "api": {"locations": ["Remote"]},
        "url_template": "x",
    }
    assert sites[1] == {
        "name": "indeed",
        "enabled": True,
        "limit": 3,
        "max_age_hours": 72,
        "filter": {"location": ["jakarta"]},
        "api": None,
        "url_template": "x",
    }


def test_config_read_gives_an_empty_filter_when_a_site_has_none(
    client: TestClient, gateway: FakeGateway
):
    config_settings = CONFIG["settings"]
    assert isinstance(config_settings, dict)
    settings = {**config_settings, "sites": {"indeed": {"limit": 3, "url_template": "x"}}}
    gateway.config = {**CONFIG, "settings": settings}

    site = client.get("/api/config").json()["data"]["values"]["sites"][0]

    assert site["filter"] == {}
    assert site["max_age_hours"] is None


def test_config_read_returns_each_site_url_template(client: TestClient, gateway: FakeGateway):
    config_settings = CONFIG["settings"]
    assert isinstance(config_settings, dict)
    stored_sites = {
        "upwork": {"limit": 30, "url_template": "https://upwork.test/search?q={keyword}"},
        "indeed": {"limit": 3},
    }
    gateway.config = {**CONFIG, "settings": {**config_settings, "sites": stored_sites}}

    sites = client.get("/api/config").json()["data"]["values"]["sites"]

    assert sites[0]["url_template"] == "https://upwork.test/search?q={keyword}"
    assert sites[1]["url_template"] is None


def test_config_read_marks_stale_values_when_mcp_is_down(client: TestClient, gateway: FakeGateway):
    client.get("/api/config")
    gateway.is_down = True

    assert client.get("/api/config").json()["data"]["is_stale"] is True


def test_config_update_sends_only_changed_fields(client: TestClient, gateway: FakeGateway):
    response = client.put(
        "/api/config",
        json={
            "version": 4,
            "sites": {
                "upwork": {
                    "limit": 9,
                    "max_age_hours": None,
                    "filter": {"work_type": ["remote"]},
                    "api": {
                        "enabled": True,
                        "locations": ["Remote"],
                        "country_wide": False,
                        "delay_seconds": [4, 6],
                    },
                }
            },
        },
    )

    assert response.status_code == 200
    assert gateway.arguments["update_config"] == {
        "patch": {
            "sites": {
                "upwork": {
                    "limit": 9,
                    "max_age_hours": None,
                    "filter": {"work_type": ["remote"]},
                    "api": {
                        "enabled": True,
                        "locations": ["Remote"],
                        "country_wide": False,
                        "delay_seconds": [4.0, 6.0],
                    },
                }
            },
        },
        "expected_version": 4,
        "source": "ui",
    }


def test_config_update_requires_version(client: TestClient):
    assert client.put("/api/config", json={"sites": SITE_LIMIT}).status_code == 422


@pytest.mark.parametrize(
    "body",
    [
        {"version": 4, "proxy_url": "socks5://localhost:1080"},
        {"version": 4, "sites": {"upwork": {"url_template": "https://evil.test"}}},
    ],
)
def test_config_update_refuses_fields_the_page_cannot_edit(client: TestClient, body: dict):
    assert client.put("/api/config", json=body).status_code == 422


def _delay_body(delay: list[float]) -> dict:
    api = {"enabled": True, "locations": [], "country_wide": False, "delay_seconds": delay}
    return {"version": 4, "sites": {"jobstreet": {"api": api}}}


@pytest.mark.parametrize(
    "body",
    [
        _delay_body([1, 61]),
        _delay_body([61, 62]),
        {"version": 4, "fields": ["title"] * 101},
    ],
)
def test_config_update_refuses_values_over_the_cap(client: TestClient, body: dict):
    assert client.put("/api/config", json=body).status_code == 422


def test_config_update_refuses_keywords(client: TestClient, gateway: FakeGateway):
    response = client.put("/api/config", json={"version": 4, "keywords": ["devops"]})

    assert response.status_code == 422
    assert "update_config" not in gateway.calls


def test_config_update_returns_409_on_conflict(client: TestClient, gateway: FakeGateway):
    gateway.save_result = {"ok": False, "reason": "conflict", "message": "changed"}

    response = client.put("/api/config", json={"version": 4, "sites": SITE_LIMIT})

    assert response.status_code == 409
    assert response.json()["error"] == "changed"


def test_config_update_returns_422_on_invalid_settings(client: TestClient, gateway: FakeGateway):
    gateway.save_result = {"ok": False, "reason": "invalid", "message": "bad filter"}

    response = client.put("/api/config", json={"version": 4, "sites": SITE_LIMIT})

    assert response.status_code == 422
    assert response.json()["error"] == "bad filter"


def test_config_history_endpoint_is_gone(client: TestClient):
    assert client.get("/api/config/history").status_code == 404


def test_config_restore_endpoint_is_gone(client: TestClient, gateway: FakeGateway):
    response = client.post("/api/config/restore", json={"version": 3, "expected_version": 4})

    assert response.status_code in (404, 405)
    assert "restore_config" not in gateway.calls


def test_prod_config_needs_login(prod_client: TestClient):
    assert prod_client.get("/api/config").status_code == 401
    assert (
        prod_client.put("/api/config", json={"version": 4, "sites": SITE_LIMIT}).status_code == 401
    )


def test_prod_config_can_be_saved_after_login(prod_client: TestClient, gateway: FakeGateway):
    prod_client.post("/api/auth/login", json={"password": PASSWORD})

    response = prod_client.put("/api/config", json={"version": 4, "sites": SITE_LIMIT})

    assert response.status_code == 200
    assert "update_config" in gateway.calls


def test_cross_site_write_is_refused(client: TestClient):
    response = client.put(
        "/api/config", json={"sites": SITE_LIMIT}, headers={"sec-fetch-site": "cross-site"}
    )

    assert response.status_code == 403


def test_prod_requires_login(prod_client: TestClient):
    assert prod_client.get("/api/sites").status_code == 401


def test_prod_login_opens_api_and_sets_safe_cookie(prod_client: TestClient):
    response = prod_client.post("/api/auth/login", json={"password": PASSWORD})

    cookie = response.headers["set-cookie"].lower()
    assert response.status_code == 200
    assert "httponly" in cookie
    assert "secure" in cookie
    assert "samesite=strict" in cookie
    assert prod_client.get("/api/sites").status_code == 200


def test_prod_wrong_password_returns_401(prod_client: TestClient):
    response = prod_client.post("/api/auth/login", json={"password": "wrong"})

    assert response.status_code == 401


def test_prod_logout_clears_session(prod_client: TestClient):
    prod_client.post("/api/auth/login", json={"password": PASSWORD})

    prod_client.post("/api/auth/logout")

    assert prod_client.get("/api/sites").status_code == 401


def test_spa_paths_fall_back_to_index(tmp_path: Path, gateway: FakeGateway, database: Any):
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "index.html").write_text("<html>app</html>")
    app = create_app(_settings(tmp_path), gateway, MongoScrapeReportRepository(database))
    with TestClient(app, base_url=LOCAL_URL) as test_client:
        assert "app" in test_client.get("/config").text
        assert test_client.get("/api/missing").status_code == 404


def test_ui_files_carry_security_headers(tmp_path: Path, gateway: FakeGateway, database: Any):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>app</html>")
    (dist / "favicon.svg").write_text("<svg></svg>")
    app = create_app(_settings(tmp_path), gateway, MongoScrapeReportRepository(database))
    with TestClient(app, base_url=LOCAL_URL) as test_client:
        responses = [
            test_client.get("/"),
            test_client.get("/config"),
            test_client.get("/favicon.svg"),
        ]

    for response in responses:
        policy = response.headers["content-security-policy"]
        assert "default-src 'self'" in policy
        assert "script-src 'self'" in policy
        assert "object-src 'none'" in policy
        assert "base-uri 'self'" in policy
        assert "frame-ancestors 'none'" in policy
        assert "'unsafe-eval'" not in policy
        assert "script-src 'self' 'unsafe-inline'" not in policy
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"


def test_favicon_files_are_served_instead_of_index(
    tmp_path: Path, gateway: FakeGateway, database: Any
):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>app</html>")
    (dist / "favicon.svg").write_text("<svg></svg>")
    (dist / "favicon.ico").write_bytes(b"\x00\x00\x01\x00")
    app = create_app(_settings(tmp_path), gateway, MongoScrapeReportRepository(database))
    with TestClient(app, base_url=LOCAL_URL) as test_client:
        svg = test_client.get("/favicon.svg")
        ico = test_client.get("/favicon.ico")

    assert svg.headers["content-type"].startswith("image/svg+xml")
    assert svg.text == "<svg></svg>"
    assert ico.content == b"\x00\x00\x01\x00"


def test_read_scrape_returns_detail_shape(client: TestClient):
    scrape = _scrape(client)
    _wait_for_finish(client, scrape["id"])

    scrape_report = _read_scrape_report(client, scrape["id"])

    assert set(scrape_report) == REPORT_FIELDS
    assert set(scrape_report["record"]) == SUMMARY_FIELDS
    assert [set(job) for job in scrape_report["jobs"]] == [JOB_FIELDS]
    assert scrape_report["jobs"][0]["title"] == "A"
    assert scrape_report["jobs"][0]["site"] == "upwork"
    assert scrape_report["jobs"][0]["matched_keyword"] == "devops"
    assert scrape_report["failures"] == []


def test_read_scrape_returns_the_full_job_object(client: TestClient, gateway: FakeGateway):
    job = {
        "site": "upwork",
        "matched_keyword": "devops",
        "title": "A",
        "company": "Acme",
        "company_id": None,
        "url": "https://example.com/1",
        "location": "Remote",
        "salary": "1000 - 2000",
        "salary_min": 1000,
        "salary_max": 2000.5,
        "posted_at": "2026-11-17T10:00:00+00:00",
        "work_type": "remote",
        "employment_type": "full_time",
        "experience_level": None,
        "requirements": "Python",
    }
    results = [{"keyword": "devops", "site": "upwork", "payload": {"jobs": [job]}}]
    gateway.scrape_result = {**SCRAPE_RESULT, "results": results}
    scrape = _scrape(client)
    _wait_for_finish(client, scrape["id"])

    stored = _read_scrape_report(client, scrape["id"])["jobs"]
    latest = client.get("/api/scrapes/latest").json()["data"]["jobs"]

    assert stored == [job]
    assert latest == [job]


def test_read_scrape_lists_failures(client: TestClient, gateway: FakeGateway):
    gateway.scrape_result = {
        "ok": False,
        "results": [],
        "errors": [{"keyword": "devops", "site": "upwork", "reason": "timeout", "attempts": []}],
    }
    scrape = _scrape(client)
    _wait_for_finish(client, scrape["id"])

    scrape_report = _read_scrape_report(client, scrape["id"])

    assert scrape_report["failures"] == [
        {"keyword": "devops", "site": "upwork", "reason": "timeout"}
    ]
    assert scrape_report["jobs"] == []
    assert "payloads" not in scrape_report


def test_running_scrape_report_has_empty_lists(client: TestClient, gateway: FakeGateway):
    gateway.scrape_delay = 0.2
    scrape = _scrape(client)

    scrape_report = _read_scrape_report(client, scrape["id"])

    assert scrape_report["record"]["status"] == "running"
    assert set(scrape_report) == REPORT_FIELDS
    assert (scrape_report["jobs"], scrape_report["failures"]) == ([], [])
    _wait_for_finish(client, scrape["id"])


def test_finished_scrape_is_stored_in_ui_runs(client: TestClient, database: Any):
    scrape = _scrape(client)
    _wait_for_finish(client, scrape["id"])

    documents = list(database[SCRAPE_REPORTS_COLLECTION].find())

    assert [document["_id"] for document in documents] == [scrape["id"]]
    assert documents[0]["record"]["status"] == "succeeded"
    assert documents[0]["payloads"] == [
        {"keyword": "devops", "site": "upwork", "filtered": {"jobs": [{"title": "A"}]}}
    ]


def test_latest_without_any_scrape_is_null(client: TestClient):
    response = client.get("/api/scrapes/latest")

    assert response.status_code == 200
    assert response.json()["data"] is None


def test_latest_returns_the_stored_scrape(client: TestClient, database: Any):
    database[SCRAPE_REPORTS_COLLECTION].insert_one(STORED_SCRAPE)

    data = client.get("/api/scrapes/latest").json()["data"]

    assert set(data) == REPORT_FIELDS
    assert data == {key: STORED_SCRAPE[key] for key in REPORT_FIELDS}


def test_read_stored_scrape_by_id(client: TestClient, database: Any):
    database[SCRAPE_REPORTS_COLLECTION].insert_one(STORED_SCRAPE)

    response = client.get(f"/api/scrapes/{STORED_SCRAPE['_id']}")

    assert response.status_code == 200
    assert set(response.json()["data"]) == REPORT_FIELDS
    assert response.json()["data"]["jobs"][0]["title"] == "Stored"


def test_latest_returns_the_current_running_run(
    client: TestClient, gateway: FakeGateway, database: Any
):
    database[SCRAPE_REPORTS_COLLECTION].insert_one(STORED_SCRAPE)
    gateway.scrape_delay = 0.2
    scrape = _scrape(client)

    data = client.get("/api/scrapes/latest").json()["data"]

    assert data["record"]["id"] == scrape["id"]
    assert data["record"]["status"] == "running"
    assert set(data) == REPORT_FIELDS
    assert (data["jobs"], data["failures"]) == ([], [])
    _wait_for_finish(client, scrape["id"])


def test_latest_returns_the_finished_current_scrape(client: TestClient):
    scrape = _scrape(client)
    _wait_for_finish(client, scrape["id"])

    data = client.get("/api/scrapes/latest").json()["data"]

    assert data["record"]["id"] == scrape["id"]
    assert data["jobs"][0]["title"] == "A"


def test_latest_needs_login(guest_client: TestClient):
    assert guest_client.get("/api/scrapes/latest").status_code == 401


def test_config_read_gives_empty_fields_when_none_are_stored(
    client: TestClient, gateway: FakeGateway
):
    settings = {"sites": {"indeed": {"limit": 3, "url_template": "x"}}}
    gateway.config = {**CONFIG, "settings": settings}

    assert client.get("/api/config").json()["data"]["values"]["fields"] == []


def test_config_update_sends_top_level_fields(client: TestClient, gateway: FakeGateway):
    body = {"version": 4, "fields": ["title", "salary_min"]}

    assert client.put("/api/config", json=body).status_code == 200
    assert gateway.arguments["update_config"]["patch"] == {"fields": ["title", "salary_min"]}


@pytest.mark.parametrize(
    "body",
    [
        {"version": 4, "default_fields": ["title"]},
        {"version": 4, "sites": {"upwork": {"fields": ["title"]}}},
    ],
)
def test_config_update_refuses_default_fields_and_site_fields(
    client: TestClient, gateway: FakeGateway, body: dict
):
    assert client.put("/api/config", json=body).status_code == 422
    assert "update_config" not in gateway.calls


def _send_latest(client: TestClient):
    return client.post("/api/scrapes/latest/discord")


def test_send_latest_scrape_starts_sending_and_keeps_the_jobs(client: TestClient):
    scrape = _scrape(client)
    _wait_for_finish(client, scrape["id"])

    response = _send_latest(client)

    assert response.status_code == 202
    assert set(response.json()["data"]) == SUMMARY_FIELDS
    assert response.json()["data"]["id"] == scrape["id"]
    assert response.json()["data"]["discord_status"] == "sending"
    scrape_summary = _wait_for_discord(client, scrape["id"])
    assert scrape_summary["discord_status"] == "sent"
    assert (scrape_summary["discord_sent"], scrape_summary["discord_failed"]) == (1, 0)
    latest = client.get("/api/scrapes/latest").json()["data"]
    assert latest["record"]["discord_status"] == "sent"
    assert latest["jobs"][0]["title"] == "A"


def test_send_latest_scrape_sends_the_stored_scrape_after_a_restart(
    client: TestClient, gateway: FakeGateway, database: Any
):
    database[SCRAPE_REPORTS_COLLECTION].insert_one(STORED_SCRAPE)

    response = _send_latest(client)

    assert response.status_code == 202
    assert response.json()["data"]["id"] == STORED_SCRAPE["_id"]
    scrape_summary = _wait_for_discord(client, STORED_SCRAPE["_id"])
    assert scrape_summary["discord_status"] == "sent"
    assert gateway.arguments["send_discord_message"] == {
        "channel_id": "123456789012345678",
        "mention": False,
        "jobs": STORED_SCRAPE["jobs"],
        "keyword_count": 1,
        "site_count": 1,
        "error_count": 0,
    }
    latest = client.get("/api/scrapes/latest").json()["data"]
    assert latest["jobs"] == STORED_SCRAPE["jobs"]
    assert latest["failures"] == STORED_SCRAPE["failures"]
    stored = database[SCRAPE_REPORTS_COLLECTION].find_one({"_id": STORED_SCRAPE["_id"]})
    assert stored["jobs"] == STORED_SCRAPE["jobs"]
    assert stored["payloads"] == STORED_SCRAPE["payloads"]


def test_send_latest_scrape_without_any_scrape_returns_404(
    client: TestClient, gateway: FakeGateway
):
    response = _send_latest(client)

    assert response.status_code == 404
    assert response.json()["error"] == "There is no run to send yet."
    assert "send_discord_message" not in gateway.calls


def test_send_latest_scrape_is_refused_while_a_scrape_is_in_progress(
    client: TestClient, gateway: FakeGateway
):
    gateway.scrape_delay = 0.2
    scrape = _scrape(client)

    response = _send_latest(client)

    assert response.status_code == 409
    assert response.json()["error"] == "A scrape is already running."
    _wait_for_finish(client, scrape["id"])
    assert "send_discord_message" not in gateway.calls


def test_send_latest_scrape_of_a_failed_scrape_returns_409(
    client: TestClient, gateway: FakeGateway, database: Any
):
    failed_scrape = {**STORED_SCRAPE, "record": {**STORED_SCRAPE["record"], "status": "failed"}}
    database[SCRAPE_REPORTS_COLLECTION].insert_one(failed_scrape)

    response = _send_latest(client)

    assert response.status_code == 409
    assert response.json()["error"] == "Only a finished run can be sent to Discord."
    assert "send_discord_message" not in gateway.calls


def test_send_latest_scrape_ends_as_failed_when_discord_is_not_configured(
    client: TestClient, gateway: FakeGateway
):
    gateway.discord_settings = {**DISCORD_SETTINGS, "configured": False}
    scrape = _scrape(client)
    _wait_for_finish(client, scrape["id"])

    response = _send_latest(client)

    assert response.status_code == 202
    scrape_summary = _wait_for_discord(client, scrape["id"])
    assert scrape_summary["discord_status"] == "failed"
    assert scrape_summary["discord_error"] == "Discord token is not configured."
    assert "send_discord_message" not in gateway.calls


def test_send_latest_scrape_needs_login(guest_client: TestClient):
    assert _send_latest(guest_client).status_code == 401


def test_send_latest_scrape_refuses_a_cross_site_request(client: TestClient):
    response = client.post("/api/scrapes/latest/discord", headers={"sec-fetch-site": "cross-site"})

    assert response.status_code == 403
