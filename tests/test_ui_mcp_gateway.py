from __future__ import annotations

import asyncio
from typing import Any

import pytest

from ui_server.errors import ConfigConflictError, ConfigInvalidError, McpUnavailableError
from ui_server.services import mcp_gateway
from ui_server.services.mcp_gateway import LocalGateway, ScraperClient, read_result

SITE_PATCH = {"sites": {"upwork": {"limit": 9}}}


class FakeGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.responses: list[dict[str, Any] | Exception] = []

    async def call(
        self, tool: str, arguments: dict[str, Any], timeout_seconds: float
    ) -> dict[str, Any]:
        self.calls.append((tool, arguments))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_read_result_returns_the_dict():
    assert read_result("list_sites", {"ok": True}) == {"ok": True}


def test_read_result_rejects_a_non_dict():
    with pytest.raises(McpUnavailableError):
        read_result("list_sites", None)


def test_read_result_passes_the_tool_error_message():
    with pytest.raises(McpUnavailableError, match="bad config"):
        read_result("list_sites", {"error": "bad config"})


def test_local_gateway_runs_a_sync_tool_with_its_arguments(monkeypatch: pytest.MonkeyPatch):
    seen: list[dict[str, Any]] = []

    def fake_update_config(**arguments: Any) -> dict[str, Any]:
        seen.append(arguments)
        return {"ok": True, "version": 2}

    monkeypatch.setitem(mcp_gateway.LOCAL_TOOLS, "update_config", fake_update_config)

    result = asyncio.run(
        LocalGateway().call("update_config", {"patch": SITE_PATCH, "source": "ui"}, 5.0)
    )

    assert result == {"ok": True, "version": 2}
    assert seen == [{"patch": SITE_PATCH, "source": "ui"}]


def test_local_gateway_awaits_an_async_tool(monkeypatch: pytest.MonkeyPatch):
    async def fake_list_channels() -> dict[str, Any]:
        return {"ok": True, "channels": []}

    monkeypatch.setitem(mcp_gateway.LOCAL_TOOLS, "list_discord_channels", fake_list_channels)

    result = asyncio.run(LocalGateway().call("list_discord_channels", {}, 5.0))

    assert result == {"ok": True, "channels": []}


def test_local_gateway_turns_a_crash_into_unavailable(monkeypatch: pytest.MonkeyPatch):
    def broken() -> dict[str, Any]:
        raise RuntimeError("mongo down")

    monkeypatch.setitem(mcp_gateway.LOCAL_TOOLS, "get_config", broken)

    with pytest.raises(McpUnavailableError):
        asyncio.run(LocalGateway().call("get_config", {}, 5.0))


def test_local_gateway_turns_a_tool_error_into_unavailable(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setitem(mcp_gateway.LOCAL_TOOLS, "get_config", lambda: {"error": "missing"})

    with pytest.raises(McpUnavailableError, match="missing"):
        asyncio.run(LocalGateway().call("get_config", {}, 5.0))


def test_local_tools_cover_every_tool_the_ui_calls():
    assert set(mcp_gateway.LOCAL_TOOLS) == {
        "list_sites",
        "get_config",
        "update_config",
        "scrape_jobs",
        "get_discord_settings",
        "save_discord_settings",
        "test_discord_connection",
        "list_discord_channels",
        "preview_discord_message",
        "send_discord_message",
    }


def test_read_returns_fresh_value():
    gateway = FakeGateway()
    gateway.responses = [{"sites": []}]

    read = asyncio.run(ScraperClient(gateway).read_sites())

    assert read.value == {"sites": []}
    assert read.is_stale is False


def test_read_falls_back_to_last_value_when_mcp_is_busy():
    gateway = FakeGateway()
    gateway.responses = [{"sites": ["a"]}, McpUnavailableError()]
    client = ScraperClient(gateway)

    async def read_twice():
        await client.read_sites()
        return await client.read_sites()

    read = asyncio.run(read_twice())

    assert read.value == {"sites": ["a"]}
    assert read.is_stale is True


def test_read_raises_when_nothing_is_cached():
    gateway = FakeGateway()
    gateway.responses = [McpUnavailableError()]

    with pytest.raises(McpUnavailableError):
        asyncio.run(ScraperClient(gateway).read_config())


def test_scrape_jobs_sends_sites_and_keywords_without_saving_the_run_and_asks_for_payloads():
    gateway = FakeGateway()
    gateway.responses = [{"ok": True}]

    asyncio.run(ScraperClient(gateway).scrape_jobs(("upwork",), ("django",)))

    assert gateway.calls == [
        (
            "scrape_jobs",
            {
                "sites": ["upwork"],
                "keywords": ["django"],
                "save_run": False,
                "include_payloads": True,
            },
        )
    ]


def test_save_config_sends_patch_version_and_source():
    gateway = FakeGateway()
    gateway.responses = [{"ok": True, "version": 2}]

    asyncio.run(ScraperClient(gateway).save_config(SITE_PATCH, 1))

    assert gateway.calls == [
        ("update_config", {"patch": SITE_PATCH, "expected_version": 1, "source": "ui"})
    ]


def test_save_config_raises_on_conflict():
    gateway = FakeGateway()
    gateway.responses = [{"ok": False, "reason": "conflict", "message": "changed"}]

    with pytest.raises(ConfigConflictError, match="changed"):
        asyncio.run(ScraperClient(gateway).save_config(SITE_PATCH, 1))


def test_save_config_raises_on_invalid_settings():
    gateway = FakeGateway()
    gateway.responses = [{"ok": False, "reason": "invalid", "message": "bad limit"}]

    with pytest.raises(ConfigInvalidError, match="bad limit"):
        asyncio.run(ScraperClient(gateway).save_config(SITE_PATCH, 1))


def test_save_config_raises_when_store_is_down():
    gateway = FakeGateway()
    gateway.responses = [{"ok": False, "reason": "unavailable", "message": "down"}]

    with pytest.raises(McpUnavailableError, match="down"):
        asyncio.run(ScraperClient(gateway).save_config(SITE_PATCH, 1))


def test_scraper_client_has_no_history_or_restore():
    client = ScraperClient(FakeGateway())

    assert not hasattr(client, "read_config_history")
    assert not hasattr(client, "restore_config")
