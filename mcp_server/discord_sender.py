from __future__ import annotations

import asyncio
import io
from collections.abc import Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import Any

import aiohttp
import discord

from mcp_server.discord_messages import MessageAttachment, OutgoingMessage

UNAUTHORIZED_STATUS = 401
FORBIDDEN_STATUSES = (403, 404)
MAX_RATELIMIT_TIMEOUT_SECONDS = 30.0
SEND_DEADLINE_SECONDS = 150.0
ERROR_TEXT_LIMIT = 200
DEADLINE_ERROR = "Stopped: send took too long"
TOKEN_REJECTED_ERROR = "Stopped after Discord rejected the token"
NETWORK_ERRORS = (discord.DiscordException, aiohttp.ClientError, OSError, TimeoutError)
CHANNEL_RESPONSE_KEYS = ("id", "name", "guild_id", "guild_name")


class DiscordFailure(Exception):
    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message

    def to_failure_result(self) -> dict[str, Any]:
        return build_failure_result(self.reason, self.message)


@dataclass(frozen=True)
class BotIdentity:
    name: str
    id: str


class DiscordRestClient:
    def __init__(self, token: str) -> None:
        self._token = token
        self._client = discord.Client(
            intents=discord.Intents.none(), max_ratelimit_timeout=MAX_RATELIMIT_TIMEOUT_SECONDS
        )
        self._channel: Any = None

    async def __aenter__(self) -> DiscordRestClient:
        try:
            await self._client.login(self._token)
        except NETWORK_ERRORS as exc:
            await self._client.close()
            raise _build_failure_from_exception(exc) from exc
        except BaseException:
            await self._client.close()
            raise
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self._client.close()

    async def fetch_bot_identity(self) -> BotIdentity:
        user = self._client.user
        if user is None:
            raise DiscordFailure("unavailable", "Discord did not return the bot account")
        return BotIdentity(name=user.name, id=str(user.id))

    async def fetch_text_channels(self) -> list[dict[str, Any]]:
        text_channel_rows: list[dict[str, Any]] = []
        try:
            async for guild in self._client.fetch_guilds(limit=None):
                guild_channels = await guild.fetch_channels()
                for channel in guild_channels:
                    if not isinstance(channel, discord.TextChannel):
                        continue
                    text_channel_rows.append(_build_text_channel_row(guild, channel))
        except NETWORK_ERRORS as exc:
            raise _build_failure_from_exception(exc) from exc
        return text_channel_rows

    async def check_channel(self, channel_id: str) -> None:
        try:
            channel = await self._client.fetch_channel(int(channel_id))
        except NETWORK_ERRORS as exc:
            raise _build_failure_from_exception(exc, channel=True) from exc
        if not hasattr(channel, "send"):
            raise DiscordFailure("forbidden", "The bot cannot post in that channel")
        self._channel = channel

    async def send_message(
        self,
        channel_id: str,
        content: str,
        mention_user_id: str | None = None,
        attachment: MessageAttachment | None = None,
    ) -> str:
        if self._channel is None:
            await self.check_channel(channel_id)
        allowed_mentions = _build_allowed_mentions(mention_user_id)
        try:
            if attachment is None:
                message = await self._channel.send(content, allowed_mentions=allowed_mentions)
            else:
                message = await self._channel.send(
                    content,
                    file=_build_discord_file(attachment),
                    allowed_mentions=allowed_mentions,
                )
        except NETWORK_ERRORS as exc:
            raise _build_failure_from_exception(exc, channel=True) from exc
        return str(message.id)


def open_client(token: str) -> DiscordRestClient:
    return DiscordRestClient(token)


async def fetch_identity(token: str) -> dict[str, Any]:
    async with open_client(token) as client:
        identity = await client.fetch_bot_identity()
    return {"ok": True, "bot_name": identity.name, "bot_id": identity.id}


async def fetch_channels(token: str) -> dict[str, Any]:
    async with open_client(token) as client:
        text_channel_rows = await client.fetch_text_channels()
    sorted_channel_rows = sorted(text_channel_rows, key=_build_channel_sort_key)
    channel_responses = []
    for channel_row in sorted_channel_rows:
        channel_responses.append(_build_channel_response(channel_row))
    return {"ok": True, "channels": channel_responses}


async def post_messages(
    token: str, channel_id: str, messages: Sequence[OutgoingMessage]
) -> dict[str, Any]:
    message_results: list[dict[str, Any]] = []
    async with open_client(token) as client:
        await client.check_channel(channel_id)
        try:
            async with asyncio.timeout(SEND_DEADLINE_SECONDS):
                await _post_messages_in_order(client, channel_id, messages, message_results)
        except TimeoutError:
            _add_deadline_results(messages, message_results)
    failed_count = _count_failed_results(message_results)
    return {
        "ok": True,
        "sent": len(message_results) - failed_count,
        "failed": failed_count,
        "results": message_results,
    }


def build_failure_result(reason: str, message: str) -> dict[str, Any]:
    return {"ok": False, "reason": reason, "message": message}


def _read_error_detail(exc: discord.HTTPException) -> str:
    error_text = " ".join(exc.text.split())[:ERROR_TEXT_LIMIT]
    if not error_text:
        return ""
    return f": {error_text}"


def _build_failure_from_exception(exc: Exception, *, channel: bool = False) -> DiscordFailure:
    if isinstance(exc, discord.LoginFailure):
        return DiscordFailure("unauthorized", "Discord rejected the bot token")
    if isinstance(exc, discord.HTTPException):
        if exc.status == UNAUTHORIZED_STATUS:
            return DiscordFailure("unauthorized", "Discord rejected the bot token")
        if channel and exc.status in FORBIDDEN_STATUSES:
            return DiscordFailure("forbidden", "The bot cannot post in that channel")
        return DiscordFailure(
            "unavailable", f"Discord returned an error ({exc.status}){_read_error_detail(exc)}"
        )
    if isinstance(exc, discord.RateLimited):
        return DiscordFailure(
            "unavailable", f"Discord rate limit hit, retry in {round(exc.retry_after)} seconds"
        )
    return DiscordFailure("unavailable", f"Discord cannot be reached ({type(exc).__name__})")


def _build_text_channel_row(guild: Any, channel: discord.TextChannel) -> dict[str, Any]:
    return {
        "id": str(channel.id),
        "name": channel.name,
        "guild_id": str(guild.id),
        "guild_name": guild.name,
        "position": channel.position,
    }


def _build_channel_sort_key(channel_row: dict[str, Any]) -> tuple[str, int]:
    return (channel_row["guild_name"].casefold(), channel_row["position"])


def _build_channel_response(channel_row: dict[str, Any]) -> dict[str, Any]:
    channel_response: dict[str, Any] = {}
    for key in CHANNEL_RESPONSE_KEYS:
        channel_response[key] = channel_row[key]
    return channel_response


def _build_allowed_mentions(mention_user_id: str | None) -> discord.AllowedMentions:
    if not mention_user_id:
        return discord.AllowedMentions(everyone=False, roles=False, users=False)
    mentioned_users = [discord.Object(id=int(mention_user_id))]
    return discord.AllowedMentions(everyone=False, roles=False, users=mentioned_users)


def _build_discord_file(attachment: MessageAttachment) -> discord.File:
    file_bytes = io.BytesIO(attachment.file_text.encode("utf-8"))
    return discord.File(file_bytes, filename=attachment.file_name)


def _build_message_result(
    index: int,
    message: OutgoingMessage,
    message_id: str | None,
    error: str | None,
) -> dict[str, Any]:
    message_status = "sent"
    if error:
        message_status = "failed"
    return {
        "index": index,
        "kind": message.kind,
        "title": message.title,
        "job_count": message.job_count,
        "status": message_status,
        "message_id": message_id,
        "error": error,
    }


async def _post_messages_in_order(
    client: DiscordRestClient,
    channel_id: str,
    messages: Sequence[OutgoingMessage],
    message_results: list[dict[str, Any]],
) -> None:
    is_token_rejected = False
    for index, message in enumerate(messages):
        if is_token_rejected:
            message_results.append(
                _build_message_result(index, message, None, TOKEN_REJECTED_ERROR)
            )
            continue
        try:
            message_id = await client.send_message(
                channel_id, message.content, message.mention_user_id, message.attachment
            )
        except DiscordFailure as exc:
            is_token_rejected = exc.reason == "unauthorized"
            message_results.append(_build_message_result(index, message, None, exc.message))
            continue
        message_results.append(_build_message_result(index, message, message_id, None))


def _add_deadline_results(
    messages: Sequence[OutgoingMessage], message_results: list[dict[str, Any]]
) -> None:
    first_unsent_index = len(message_results)
    for index in range(first_unsent_index, len(messages)):
        message_results.append(_build_message_result(index, messages[index], None, DEADLINE_ERROR))


def _count_failed_results(message_results: list[dict[str, Any]]) -> int:
    failed_count = 0
    for message_result in message_results:
        if message_result["status"] == "failed":
            failed_count += 1
    return failed_count
