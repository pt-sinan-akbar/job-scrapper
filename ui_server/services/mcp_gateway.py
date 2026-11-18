from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from mcp_server import discord_tools, server
from ui_server.errors import (
    ConfigConflictError,
    ConfigInvalidError,
    DiscordForbiddenError,
    DiscordNotConfiguredError,
    DiscordUnauthorizedError,
    McpUnavailableError,
)

LOG = logging.getLogger("scraper-ui")
READ_TIMEOUT_SECONDS = 5.0
WRITE_TIMEOUT_SECONDS = 10.0
SCRAPE_TIMEOUT_SECONDS = 1800.0
DISCORD_CALL_TIMEOUT_SECONDS = 20.0
DISCORD_SEND_TIMEOUT_SECONDS = 180.0
SAVE_SOURCE = "ui"


class McpGateway(Protocol):
    async def call(
        self, tool: str, arguments: dict[str, Any], timeout_seconds: float
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class CachedRead:
    value: dict[str, Any]
    is_stale: bool


LOCAL_TOOLS: dict[str, Callable[..., Any]] = {
    tool.__name__: tool
    for tool in (
        server.list_sites,
        server.get_config,
        server.update_config,
        server.scrape_jobs,
        *discord_tools.DISCORD_TOOLS,
    )
}


def read_result(tool: str, result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        LOG.warning("tool %s returned no usable result", tool)
        raise McpUnavailableError()
    if "error" in result:
        raise McpUnavailableError(str(result["error"]))
    return result


def _raise_on_failed_save(result: dict[str, Any]) -> None:
    if result.get("ok"):
        return
    reason = result.get("reason")
    message = result.get("message")
    if reason == "conflict":
        raise ConfigConflictError(message)
    if reason == "invalid":
        raise ConfigInvalidError(message)
    raise McpUnavailableError(message)


def _raise_on_failed_discord(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("ok"):
        return result
    reason = result.get("reason")
    message = result.get("message")
    if reason == "not_configured":
        raise DiscordNotConfiguredError()
    if reason == "unauthorized":
        raise DiscordUnauthorizedError()
    if reason == "forbidden":
        raise DiscordForbiddenError()
    if reason == "invalid":
        raise ConfigInvalidError(message)
    raise McpUnavailableError(message)


def _message_arguments(
    mention: bool, text: str | None, jobs: list[dict[str, Any]] | None
) -> dict[str, Any]:
    content: dict[str, Any] = {"text": text} if text is not None else {"jobs": jobs}
    return {"mention": mention, **content}


async def _run_tool(function: Callable[..., Any], arguments: dict[str, Any]) -> Any:
    if inspect.iscoroutinefunction(function):
        return await function(**arguments)
    return await asyncio.to_thread(function, **arguments)


class LocalGateway:
    async def call(
        self, tool: str, arguments: dict[str, Any], timeout_seconds: float
    ) -> dict[str, Any]:
        try:
            result = await _run_tool(LOCAL_TOOLS[tool], arguments)
        except Exception as exc:
            LOG.warning("tool %s failed", tool, exc_info=exc)
            raise McpUnavailableError() from exc
        return read_result(tool, result)


class ScraperClient:
    def __init__(self, gateway: McpGateway) -> None:
        self._gateway = gateway
        self._cache: dict[str, dict[str, Any]] = {}

    async def scrape_jobs(
        self, sites: tuple[str, ...], keywords: tuple[str, ...]
    ) -> dict[str, Any]:
        arguments = {
            "sites": list(sites),
            "keywords": list(keywords),
            "save_run": False,
            "include_payloads": True,
        }
        return await self._gateway.call("scrape_jobs", arguments, SCRAPE_TIMEOUT_SECONDS)

    async def read_sites(self) -> CachedRead:
        return await self._read("list_sites")

    async def read_config(self) -> CachedRead:
        return await self._read("get_config")

    async def save_config(self, patch: dict[str, Any], expected_version: int) -> None:
        arguments = {"patch": patch, "expected_version": expected_version, "source": SAVE_SOURCE}
        result = await self._gateway.call("update_config", arguments, WRITE_TIMEOUT_SECONDS)
        _raise_on_failed_save(result)

    async def read_discord_settings(self) -> dict[str, Any]:
        return await self._gateway.call("get_discord_settings", {}, READ_TIMEOUT_SECONDS)

    async def save_discord_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        result = await self._gateway.call(
            "save_discord_settings", {"patch": patch}, WRITE_TIMEOUT_SECONDS
        )
        return _raise_on_failed_discord(result)["settings"]

    async def test_discord_connection(self) -> dict[str, Any]:
        result = await self._gateway.call(
            "test_discord_connection", {}, DISCORD_CALL_TIMEOUT_SECONDS
        )
        _raise_on_failed_discord(result)
        return {"bot_name": result["bot_name"], "bot_id": result["bot_id"]}

    async def list_discord_channels(self) -> list[dict[str, Any]]:
        result = await self._gateway.call("list_discord_channels", {}, DISCORD_CALL_TIMEOUT_SECONDS)
        return _raise_on_failed_discord(result)["channels"]

    async def preview_discord_message(
        self, mention: bool, text: str | None, jobs: list[dict[str, Any]] | None
    ) -> list[str]:
        result = await self._gateway.call(
            "preview_discord_message", _message_arguments(mention, text, jobs), READ_TIMEOUT_SECONDS
        )
        return _raise_on_failed_discord(result)["messages"]

    async def send_discord_message(
        self, channel_id: str, mention: bool, text: str | None, jobs: list[dict[str, Any]] | None
    ) -> dict[str, Any]:
        arguments = {"channel_id": channel_id, **_message_arguments(mention, text, jobs)}
        result = await self._gateway.call(
            "send_discord_message", arguments, DISCORD_SEND_TIMEOUT_SECONDS
        )
        _raise_on_failed_discord(result)
        return {"sent": result["sent"], "failed": result["failed"], "results": result["results"]}

    async def _read(self, tool: str) -> CachedRead:
        try:
            value = await self._gateway.call(tool, {}, READ_TIMEOUT_SECONDS)
        except McpUnavailableError:
            if tool not in self._cache:
                raise
            return CachedRead(self._cache[tool], True)
        self._cache = {**self._cache, tool: value}
        return CachedRead(value, False)
