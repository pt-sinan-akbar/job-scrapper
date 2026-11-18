from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from ui_server.app import create_app
from ui_server.errors import McpUnavailableError
from ui_server.settings import Settings

PASSWORD = "correct horse battery"  # pragma: allowlist secret
DEV_LOGIN_KEY = "dev-login-key-for-tests"
LOCAL_URL = "http://127.0.0.1:8090"
SITES = {
    "keywords": ["devops"],
    "limit": 3,
    "sites": [{"name": "upwork", "enabled": True, "url_template": "x", "sample_url": "x"}],
}
CONFIG = {
    "version": 4,
    "updated_at": "2026-11-02T01:00:00+00:00",
    "updated_by": "ui",
    "settings": {
        "keywords": ["devops"],
        "limit": 3,
        "max_age_hours": 72,
        "filter": {"location": "jakarta", "work_type": []},
        "default_fields": ["title"],
        "sites": {
            "upwork": {
                "enabled": True,
                "limit": 30,
                "filter": {},
                "url_template": "x",
                "api": {"locations": ["Remote"]},
            },
            "indeed": {"url_template": "x"},
        },
    },
    "job_fields": ["site", "title", "salary_min"],
    "mandatory_fields": ["site", "title"],
    "location_options": {"jobstreet": [{"label": "Jakarta", "value": "Jakarta Raya"}]},
}
SAVED = {"ok": True, "version": 5}
DISCORD_SETTINGS = {
    "configured": True,
    "default_channel_id": "123456789012345678",
    "mention_user_id": "",
}
SCRAPE_RESULT = {
    "ok": True,
    "results": [{"keyword": "devops", "sites": [{"site": "upwork", "jobs": [{"title": "A"}]}]}],
    "errors": [],
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
                "sent": 2,
                "failed": 0,
                "results": [
                    {"kind": "job", "status": "sent"},
                    {"kind": "summary", "status": "sent"},
                ],
            },
        }
        return responses[tool]


def _settings(tmp_path: Path, **overrides: Any) -> Settings:
    values = {
        "env": "dev",
        "dev_login_key": DEV_LOGIN_KEY,
        "static_dir": tmp_path / "dist",
    }
    return Settings(**{**values, **overrides})


def _prod_settings(tmp_path: Path) -> Settings:
    return _settings(
        tmp_path,
        env="prod",
        password_hash=PasswordHasher().hash(PASSWORD),
        session_secret="s" * 32,
        domain="testserver",
    )


@pytest.fixture
def gateway() -> FakeGateway:
    return FakeGateway()


@pytest.fixture
def guest_client(tmp_path: Path, gateway: FakeGateway):
    app = create_app(_settings(tmp_path), gateway)
    with TestClient(app, base_url=LOCAL_URL) as test_client:
        yield test_client


@pytest.fixture
def client(guest_client: TestClient):
    guest_client.post("/api/auth/login", json={"password": DEV_LOGIN_KEY})
    return guest_client


@pytest.fixture
def prod_client(tmp_path: Path, gateway: FakeGateway):
    app = create_app(_prod_settings(tmp_path), gateway)
    with TestClient(app, base_url="https://testserver") as test_client:
        yield test_client


def _run(client: TestClient) -> dict:
    response = client.post("/api/runs", json={"keywords": ["devops"], "sites": ["upwork"]})
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


def test_dev_login_key_opens_api(guest_client: TestClient):
    response = guest_client.post("/api/auth/login", json={"password": DEV_LOGIN_KEY})

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

    assert data["keywords"] == ["devops"]
    assert data["sites"] == [{"name": "upwork", "enabled": True}]
    assert data["is_stale"] is False


def test_sites_returns_503_when_mcp_is_down(client: TestClient, gateway: FakeGateway):
    gateway.is_down = True

    response = client.get("/api/sites")

    assert response.status_code == 503
    assert response.json()["success"] is False


RECORD_FIELDS = {
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


def _read_record(client: TestClient, run_id: str) -> dict:
    return client.get(f"/api/runs/{run_id}").json()["data"]


def _wait_for(client: TestClient, run_id: str, is_pending: Any) -> dict:
    deadline = time.monotonic() + 2
    record = _read_record(client, run_id)
    while is_pending(record) and time.monotonic() < deadline:
        time.sleep(0.01)
        record = _read_record(client, run_id)
    return record


def _wait_for_finish(client: TestClient, run_id: str) -> dict:
    return _wait_for(client, run_id, lambda record: record["status"] == "running")


def _wait_for_discord(client: TestClient, run_id: str) -> dict:
    return _wait_for(client, run_id, lambda record: record["discord_status"] == "sending")


def test_start_run_then_read_record(client: TestClient):
    run = _run(client)

    record = _wait_for_finish(client, run["id"])

    assert set(record) == RECORD_FIELDS
    assert record["id"] == run["id"]
    assert record["status"] == "succeeded"
    assert record["job_count"] == 1
    assert record["keywords"] == ["devops"]
    assert record["sites"] == ["upwork"]
    assert record["finished_at"] is not None


def test_read_run_keeps_record_after_finish(client: TestClient):
    run = _run(client)
    _wait_for_finish(client, run["id"])

    response = client.get(f"/api/runs/{run['id']}")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "succeeded"


def test_new_run_replaces_previous_record(client: TestClient):
    first = _run(client)
    _wait_for_finish(client, first["id"])
    second = _run(client)

    assert client.get(f"/api/runs/{first['id']}").status_code == 404
    assert _wait_for_finish(client, second["id"])["id"] == second["id"]


def test_read_run_reports_failed_scrape(client: TestClient, gateway: FakeGateway):
    gateway.scrape_result = {"ok": False, "results": [], "errors": [{"site": "upwork"}]}
    run = _run(client)

    record = _wait_for_finish(client, run["id"])

    assert record["status"] == "failed"
    assert record["error_count"] == 1


def test_scrape_does_not_ask_for_payloads(client: TestClient, gateway: FakeGateway):
    run = _run(client)
    _wait_for_finish(client, run["id"])

    assert gateway.arguments["scrape_jobs"] == {
        "sites": ["upwork"],
        "keywords": ["devops"],
        "save_run": False,
    }


def test_start_run_without_notify_has_no_discord_status(client: TestClient, gateway: FakeGateway):
    run = _run(client)

    record = _wait_for_finish(client, run["id"])

    assert record["discord_status"] is None
    assert "send_discord_message" not in gateway.calls


def test_start_run_with_notify_sends_to_discord(client: TestClient, gateway: FakeGateway):
    response = client.post(
        "/api/runs",
        json={"keywords": ["devops"], "sites": ["upwork"], "notify_discord": True},
    )
    assert response.status_code == 202

    run_id = response.json()["data"]["id"]
    _wait_for_finish(client, run_id)
    record = _wait_for_discord(client, run_id)

    assert record["status"] == "succeeded"
    assert record["discord_status"] == "sent"
    assert (record["discord_sent"], record["discord_failed"]) == (1, 0)
    assert gateway.arguments["send_discord_message"] == {
        "channel_id": "123456789012345678",
        "mention": False,
        "jobs": [{"title": "A"}],
    }


def test_start_run_rejects_non_boolean_notify(client: TestClient):
    response = client.post(
        "/api/runs",
        json={"keywords": ["devops"], "sites": ["upwork"], "notify_discord": "maybe"},
    )

    assert response.status_code == 422


def test_run_list_endpoint_is_gone(client: TestClient):
    assert client.get("/api/runs").status_code in (404, 405)


def test_log_stream_endpoint_is_gone(client: TestClient):
    assert client.get("/api/logs/stream").status_code == 404


def test_second_run_is_refused_before_reading_sites(client: TestClient, gateway: FakeGateway):
    gateway.scrape_delay = 0.2
    run = _run(client)
    gateway.calls.clear()

    response = client.post("/api/runs", json={"keywords": ["devops"], "sites": ["upwork"]})

    assert response.status_code == 409
    assert "list_sites" not in gateway.calls
    _wait_for_finish(client, run["id"])


def test_start_run_rejects_unknown_site(client: TestClient):
    response = client.post("/api/runs", json={"keywords": ["devops"], "sites": ["ghost"]})

    assert response.status_code == 422


def test_start_run_needs_keywords(client: TestClient):
    response = client.post("/api/runs", json={"keywords": [], "sites": ["upwork"]})

    assert response.status_code == 422


def test_unknown_run_returns_404(client: TestClient):
    assert client.get("/api/runs/nope").status_code == 404


def test_config_read_returns_values_and_version(client: TestClient):
    data = client.get("/api/config").json()["data"]

    assert data["version"] == 4
    assert data["updated_by"] == "ui"
    assert data["is_stale"] is False
    assert data["values"]["filter"] == {"location": ["jakarta"]}
    assert "proxy_url" not in data["values"]


def test_config_read_returns_concurrency(client: TestClient, gateway: FakeGateway):
    data = client.get("/api/config").json()["data"]

    assert data["values"]["concurrency"] is None


def test_config_update_sends_concurrency(client: TestClient, gateway: FakeGateway):
    response = client.put("/api/config", json={"version": 4, "concurrency": 3})

    assert response.status_code == 200
    assert gateway.arguments["update_config"]["patch"] == {"concurrency": 3}


@pytest.mark.parametrize("value", [0, 11, 2.5])
def test_config_update_refuses_concurrency_out_of_range(client: TestClient, value: float):
    assert client.put("/api/config", json={"version": 4, "concurrency": value}).status_code == 422


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

    assert sites[0]["filter"] == {}
    assert sites[0]["api"] == {"locations": ["Remote"]}
    assert sites[1] == {
        "name": "indeed",
        "enabled": True,
        "limit": None,
        "max_age_hours": None,
        "filter": None,
        "fields": None,
        "api": None,
    }


def test_config_read_marks_stale_values_when_mcp_is_down(client: TestClient, gateway: FakeGateway):
    client.get("/api/config")
    gateway.is_down = True

    assert client.get("/api/config").json()["data"]["is_stale"] is True


def test_config_update_sends_only_changed_fields(client: TestClient, gateway: FakeGateway):
    response = client.put(
        "/api/config",
        json={
            "version": 4,
            "limit": 9,
            "sites": {
                "upwork": {
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
            "limit": 9,
            "sites": {
                "upwork": {
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
    assert client.put("/api/config", json={"limit": 9}).status_code == 422


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
        {"version": 4, "keywords": ["devops"] * 101},
    ],
)
def test_config_update_refuses_values_over_the_cap(client: TestClient, body: dict):
    assert client.put("/api/config", json=body).status_code == 422


def test_config_update_returns_409_on_conflict(client: TestClient, gateway: FakeGateway):
    gateway.save_result = {"ok": False, "reason": "conflict", "message": "changed"}

    response = client.put("/api/config", json={"version": 4, "limit": 9})

    assert response.status_code == 409
    assert response.json()["error"] == "changed"


def test_config_update_returns_422_on_invalid_settings(client: TestClient, gateway: FakeGateway):
    gateway.save_result = {"ok": False, "reason": "invalid", "message": "bad filter"}

    response = client.put("/api/config", json={"version": 4, "limit": 9})

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
    assert prod_client.put("/api/config", json={"version": 4, "limit": 9}).status_code == 401


def test_prod_config_can_be_saved_after_login(prod_client: TestClient, gateway: FakeGateway):
    prod_client.post("/api/auth/login", json={"password": PASSWORD})

    response = prod_client.put("/api/config", json={"version": 4, "limit": 9})

    assert response.status_code == 200
    assert "update_config" in gateway.calls


def test_cross_site_write_is_refused(client: TestClient):
    response = client.put(
        "/api/config", json={"limit": 9}, headers={"sec-fetch-site": "cross-site"}
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


def test_spa_paths_fall_back_to_index(tmp_path: Path, gateway: FakeGateway):
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "index.html").write_text("<html>app</html>")
    app = create_app(_settings(tmp_path), gateway)
    with TestClient(app, base_url=LOCAL_URL) as test_client:
        assert "app" in test_client.get("/config").text
        assert test_client.get("/api/missing").status_code == 404


def test_favicon_files_are_served_instead_of_index(tmp_path: Path, gateway: FakeGateway):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html>app</html>")
    (dist / "favicon.svg").write_text("<svg></svg>")
    (dist / "favicon.ico").write_bytes(b"\x00\x00\x01\x00")
    app = create_app(_settings(tmp_path), gateway)
    with TestClient(app, base_url=LOCAL_URL) as test_client:
        svg = test_client.get("/favicon.svg")
        ico = test_client.get("/favicon.ico")

    assert svg.headers["content-type"].startswith("image/svg+xml")
    assert svg.text == "<svg></svg>"
    assert ico.content == b"\x00\x00\x01\x00"
