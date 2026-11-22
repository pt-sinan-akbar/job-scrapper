from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from backend.errors import (
    ConfigConflictError,
    ConfigInvalidError,
    DiscordForbiddenError,
    DiscordNotConfiguredError,
    DiscordUnauthorizedError,
    McpUnavailableError,
)
from mcp_server import discord_tools, server

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
    tool_response: dict[str, Any]
    is_stale: bool


LOCAL_TOOL_FUNCTIONS: tuple[Callable[..., Any], ...] = (
    server.list_sites,
    server.get_config,
    server.update_config,
    server.scrape_jobs,
    *discord_tools.DISCORD_TOOLS,
)


def index_tools_by_name(
    tool_functions: tuple[Callable[..., Any], ...],
) -> dict[str, Callable[..., Any]]:
    tools_by_name: dict[str, Callable[..., Any]] = {}
    for tool_function in tool_functions:
        tools_by_name[tool_function.__name__] = tool_function
    return tools_by_name


LOCAL_TOOLS = index_tools_by_name(LOCAL_TOOL_FUNCTIONS)


def read_tool_response(tool: str, tool_response: Any) -> dict[str, Any]:
    if not isinstance(tool_response, dict):
        LOG.warning("tool %s returned no usable result", tool)
        raise McpUnavailableError()
    if "error" in tool_response:
        raise McpUnavailableError(str(tool_response["error"]))
    return tool_response


class LocalGateway:
    async def call(
        self, tool: str, arguments: dict[str, Any], timeout_seconds: float
    ) -> dict[str, Any]:
        try:
            tool_response = await _call_local_tool(LOCAL_TOOLS[tool], arguments)
        except Exception as exc:
            LOG.warning("tool %s failed", tool, exc_info=exc)
            raise McpUnavailableError() from exc
        return read_tool_response(tool, tool_response)


class ScraperClient:
    def __init__(self, gateway: McpGateway) -> None:
        self._gateway = gateway
        self._cache: dict[str, dict[str, Any]] = {}

    async def scrape_jobs(
        self,
        sites: tuple[str, ...],
        keywords: tuple[str, ...],
        location: str | None = None,
        max_age_hours: int | None = None,
    ) -> dict[str, Any]:
        arguments = _build_scrape_arguments(sites, keywords, location, max_age_hours)
        return await self._gateway.call("scrape_jobs", arguments, SCRAPE_TIMEOUT_SECONDS)

    async def read_sites(self) -> CachedRead:
        return await self._read_with_cache("list_sites")

    async def read_config(self) -> CachedRead:
        return await self._read_with_cache("get_config")

    async def save_config(self, patch: dict[str, Any], expected_version: int) -> None:
        arguments = {"patch": patch, "expected_version": expected_version, "source": SAVE_SOURCE}
        save_response = await self._gateway.call("update_config", arguments, WRITE_TIMEOUT_SECONDS)
        _raise_on_failed_save(save_response)

    async def read_discord_settings(self) -> dict[str, Any]:
        return await self._gateway.call("get_discord_settings", {}, READ_TIMEOUT_SECONDS)

    async def save_discord_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        save_response = await self._gateway.call(
            "save_discord_settings", {"patch": patch}, WRITE_TIMEOUT_SECONDS
        )
        return _raise_on_failed_discord(save_response)["settings"]

    async def test_discord_connection(self) -> dict[str, Any]:
        connection_response = await self._gateway.call(
            "test_discord_connection", {}, DISCORD_CALL_TIMEOUT_SECONDS
        )
        _raise_on_failed_discord(connection_response)
        return {
            "bot_name": connection_response["bot_name"],
            "bot_id": connection_response["bot_id"],
        }

    async def list_discord_channels(self) -> list[dict[str, Any]]:
        channels_response = await self._gateway.call(
            "list_discord_channels", {}, DISCORD_CALL_TIMEOUT_SECONDS
        )
        return _raise_on_failed_discord(channels_response)["channels"]

    async def preview_discord_message(
        self, mention: bool, text: str | None, jobs: list[dict[str, Any]] | None
    ) -> list[str]:
        message_arguments = _build_message_arguments(mention, text, jobs)
        preview_response = await self._gateway.call(
            "preview_discord_message", message_arguments, READ_TIMEOUT_SECONDS
        )
        return _raise_on_failed_discord(preview_response)["messages"]

    async def send_discord_message(
        self,
        channel_id: str,
        mention: bool,
        text: str | None,
        jobs: list[dict[str, Any]] | None,
        digest_counts: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        message_arguments = _build_message_arguments(mention, text, jobs, digest_counts)
        arguments = {"channel_id": channel_id, **message_arguments}
        send_response = await self._gateway.call(
            "send_discord_message", arguments, DISCORD_SEND_TIMEOUT_SECONDS
        )
        _raise_on_failed_discord(send_response)
        return {
            "sent": send_response["sent"],
            "failed": send_response["failed"],
            "results": send_response["results"],
        }

    async def _read_with_cache(self, tool: str) -> CachedRead:
        try:
            tool_response = await self._gateway.call(tool, {}, READ_TIMEOUT_SECONDS)
        except McpUnavailableError:
            if tool not in self._cache:
                raise
            return CachedRead(self._cache[tool], True)
        self._cache = {**self._cache, tool: tool_response}
        return CachedRead(tool_response, False)


def _build_scrape_arguments(
    sites: tuple[str, ...],
    keywords: tuple[str, ...],
    location: str | None,
    max_age_hours: int | None,
) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "sites": list(sites),
        "keywords": list(keywords),
        "save_run": False,
    }
    if location is not None:
        arguments = {**arguments, "location": location}
    if max_age_hours is not None:
        arguments = {**arguments, "max_age_hours": max_age_hours}
    return arguments


def _raise_on_failed_save(save_response: dict[str, Any]) -> None:
    if save_response.get("ok"):
        return
    reason = save_response.get("reason")
    message = save_response.get("message")
    if reason == "conflict":
        raise ConfigConflictError(message)
    if reason == "invalid":
        raise ConfigInvalidError(message)
    raise McpUnavailableError(message)


def _raise_on_failed_discord(discord_response: dict[str, Any]) -> dict[str, Any]:
    if discord_response.get("ok"):
        return discord_response
    reason = discord_response.get("reason")
    message = discord_response.get("message")
    if reason == "not_configured":
        raise DiscordNotConfiguredError()
    if reason == "unauthorized":
        raise DiscordUnauthorizedError()
    if reason == "forbidden":
        raise DiscordForbiddenError()
    if reason == "invalid":
        raise ConfigInvalidError(message)
    raise McpUnavailableError(message)


def _build_message_arguments(
    mention: bool,
    text: str | None,
    jobs: list[dict[str, Any]] | None,
    digest_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    if text is not None:
        return {"mention": mention, "text": text}
    if digest_counts is None:
        return {"mention": mention, "jobs": jobs}
    return {"mention": mention, "jobs": jobs, **digest_counts}


async def _call_local_tool(function: Callable[..., Any], arguments: dict[str, Any]) -> Any:
    if inspect.iscoroutinefunction(function):
        return await function(**arguments)
    return await asyncio.to_thread(function, **arguments)
