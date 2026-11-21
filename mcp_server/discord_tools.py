from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from starlette.concurrency import run_in_threadpool

from mcp_server import discord_sender, mongo
from mcp_server.discord_messages import (
    DigestCounts,
    MessageInvalidError,
    OutgoingMessage,
    build_messages,
)
from mcp_server.discord_sender import DiscordFailure, build_failure_result
from mcp_server.discord_settings import (
    DiscordSettingsInvalidError,
    DiscordSettingsStore,
    StoredDiscordSettings,
    build_settings_payload,
    is_snowflake,
)
from scraper.config_loader import ConfigError

LOG = logging.getLogger(__name__)


def get_discord_settings() -> dict[str, Any]:
    """Return the Discord settings, with the bot token masked.

    The token itself is never returned, only token_hint (for example "••••1234").
    message_template and max_chars fall back to built-in defaults until they
    are saved.

    Returns:
        {configured, token_hint, default_channel_id, mention_user_id,
        message_template, max_chars, updated_at}. configured is true when a
        token is saved. On failure: {error: str}.
    """
    try:
        return build_settings_payload(_build_discord_settings_store().read())
    except ConfigError as exc:
        return {"error": str(exc)}


def save_discord_settings(patch: dict[str, Any]) -> dict[str, Any]:
    """Change the Discord settings. Keys left out keep their current value.

    Args:
        patch: changes to apply. Allowed keys:
            token: non-empty string, replaces the saved token (it cannot be cleared)
            default_channel_id: 17 to 20 digit string, or null or "" to clear
            mention_user_id: 17 to 20 digit string, or null or "" to clear
            message_template: non-empty text with placeholders like {title},
                {company}, {location}, {url}; a missing field becomes empty text
            max_chars: whole number from 1 to 2000, kept for older setups; job sends
                ignore it and put every job in full in the attached file

    Returns:
        On success: {ok: True, settings} with the same shape as get_discord_settings.
        On failure: {ok: False, reason, message}. reason is "invalid" or "unavailable".
    """
    try:
        saved_settings = _build_discord_settings_store().save(patch)
        return {"ok": True, "settings": build_settings_payload(saved_settings)}
    except DiscordSettingsInvalidError as exc:
        return build_failure_result("invalid", str(exc))
    except ConfigError as exc:
        return build_failure_result("unavailable", str(exc))


async def test_discord_connection() -> dict[str, Any]:
    """Check that the saved bot token works, by logging in to Discord.

    Returns:
        On success: {ok: True, bot_name, bot_id}.
        On failure: {ok: False, reason, message}. reason is "not_configured",
        "unauthorized", or "unavailable".
    """

    async def test_with_settings(settings: StoredDiscordSettings) -> dict[str, Any]:
        return await discord_sender.fetch_identity(_require_discord_token(settings))

    return await _call_with_discord_settings(test_with_settings)


async def list_discord_channels() -> dict[str, Any]:
    """List the text and announcement channels the bot can see.

    Channels are sorted by server name, then by their position in the server.

    Returns:
        On success: {ok: True, channels: [{id, name, guild_id, guild_name}]}.
        On failure: {ok: False, reason, message}. reason is "not_configured",
        "unauthorized", or "unavailable".
    """

    async def list_with_settings(settings: StoredDiscordSettings) -> dict[str, Any]:
        return await discord_sender.fetch_channels(_require_discord_token(settings))

    return await _call_with_discord_settings(list_with_settings)


def preview_discord_message(
    mention: bool,
    text: str | None = None,
    jobs: list[dict[str, Any]] | None = None,
    keyword_count: int | None = None,
    site_count: int | None = None,
    error_count: int | None = None,
) -> dict[str, Any]:
    """Build the exact message send_discord_message would post, without sending.

    Needs no token. Give exactly one of text or jobs. Text becomes one message.
    Jobs become one message with one attached markdown file named
    jobs-YYYY-MM-DD.md (date in Asia/Jakarta). The file holds every job filled
    into the saved message_template, jobs split by a "---" line, never cut.
    The message reads "**Job digest — <weekday>, <day> <month> <year>**" then
    "*Scraped N jobs across K keyword(s) and S site(s). Errors: E.*". With
    mention true and a mention_user_id saved, the message starts with a mention
    of that user.

    Args:
        mention: mention the saved user at the start of the message.
        text: free text in markdown, up to 2000 characters including the mention.
        jobs: 1 or more job dicts, using the same field names as scrape_jobs
            results. The file must stay under 10,000,000 bytes.
        keyword_count: keywords the run searched, only for jobs. Defaults to the
            distinct matched_keyword values in jobs.
        site_count: sites the run searched, only for jobs. Defaults to the
            distinct site values in jobs.
        error_count: errors in the run, only for jobs. Defaults to 0.

    Returns:
        On success: {ok: True, messages: [str], files: [{file_name, file_text}]}.
        messages holds the one message text, files holds the jobs file or is
        empty for a text message.
        On failure: {ok: False, reason, message}. reason is "invalid" or "unavailable".
    """
    try:
        settings = _build_discord_settings_store().read()
        counts = DigestCounts(keyword_count, site_count, error_count)
        messages = build_messages(settings, mention, text, jobs, counts)
    except MessageInvalidError as exc:
        return build_failure_result("invalid", str(exc))
    except ConfigError as exc:
        return build_failure_result("unavailable", str(exc))
    return {
        "ok": True,
        "messages": [message.content for message in messages],
        "files": _list_preview_files(messages),
    }


async def send_discord_message(
    channel_id: str,
    mention: bool,
    text: str | None = None,
    jobs: list[dict[str, Any]] | None = None,
    keyword_count: int | None = None,
    site_count: int | None = None,
    error_count: int | None = None,
) -> dict[str, Any]:
    """Post one message to a Discord channel.

    Same content rules as preview_discord_message: give exactly one of text or
    jobs. Jobs are posted as one message with the jobs markdown file attached.
    Only the saved user can be mentioned, never everyone or roles, and a
    mention written inside job text never pings anyone.

    Args:
        channel_id: 17 to 20 digit channel id.
        mention: mention the saved user at the start of the message.
        text: free text in markdown, up to 2000 characters including the mention.
        jobs: 1 or more job dicts, using the same field names as scrape_jobs
            results. A file over 10,000,000 bytes is refused as "invalid".
        keyword_count: keywords the run searched, only for jobs. Defaults to the
            distinct matched_keyword values in jobs.
        site_count: sites the run searched, only for jobs. Defaults to the
            distinct site values in jobs.
        error_count: errors in the run, only for jobs. Defaults to 0.

    Returns:
        On success: {ok: True, sent, failed, results: [{index, kind, title,
        job_count, status, message_id, error}]}. sent and failed count
        messages. kind is "text" or "file". For a file, title is the file name
        and job_count is the number of jobs in it, all sent or all failed
        together. For text, title is null and job_count is 0. status is "sent"
        or "failed".
        On failure before sending: {ok: False, reason, message}. reason is
        "not_configured", "invalid", "unauthorized", "forbidden" (the bot cannot
        post in that channel), or "unavailable".
    """

    async def send_with_settings(settings: StoredDiscordSettings) -> dict[str, Any]:
        token = _require_discord_token(settings)
        if not is_snowflake(channel_id):
            raise MessageInvalidError("channel_id must be a 17 to 20 digit string")
        counts = DigestCounts(keyword_count, site_count, error_count)
        messages = build_messages(settings, mention, text, jobs, counts)
        return await discord_sender.post_messages(token, channel_id, messages)

    return await _call_with_discord_settings(send_with_settings)


def _build_discord_settings_store() -> DiscordSettingsStore:
    return DiscordSettingsStore(mongo.read_database())


async def _call_with_discord_settings(
    call_with_settings: Callable[[StoredDiscordSettings], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    try:
        discord_settings = await run_in_threadpool(_build_discord_settings_store().read)
        return await call_with_settings(discord_settings)
    except DiscordFailure as exc:
        return exc.to_failure_result()
    except MessageInvalidError as exc:
        return build_failure_result("invalid", str(exc))
    except ConfigError as exc:
        return build_failure_result("unavailable", str(exc))
    except Exception:
        LOG.exception("Discord request failed")
        return build_failure_result("unavailable", "Discord request failed")


def _require_discord_token(settings: StoredDiscordSettings) -> str:
    if not settings.token:
        raise DiscordFailure("not_configured", "Discord is not set up, save a bot token first")
    return settings.token


def _list_preview_files(messages: tuple[OutgoingMessage, ...]) -> list[dict[str, str]]:
    preview_files = []
    for message in messages:
        if message.attachment is None:
            continue
        preview_files.append(
            {
                "file_name": message.attachment.file_name,
                "file_text": message.attachment.file_text,
            }
        )
    return preview_files


DISCORD_TOOLS = (
    get_discord_settings,
    save_discord_settings,
    test_discord_connection,
    list_discord_channels,
    preview_discord_message,
    send_discord_message,
)
