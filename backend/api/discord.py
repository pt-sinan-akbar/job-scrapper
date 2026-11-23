from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from backend.api.openapi_docs import (
    DISCORD_TAG,
    PREVIEW_DISCORD_MESSAGE_DOCS,
    PROTECTED_ROUTER_RESPONSES,
    READ_DISCORD_CHANNELS_DOCS,
    READ_DISCORD_SETTINGS_DOCS,
    SAVE_DISCORD_SETTINGS_DOCS,
    SEND_DISCORD_MESSAGE_DOCS,
    TEST_DISCORD_DOCS,
)
from backend.dependencies import ServicesDep, require_session
from backend.schemas.discord import (
    DiscordMessageRequest,
    DiscordSendRequest,
    DiscordSettingsRequest,
)
from backend.schemas.response import build_ok_response

router = APIRouter(
    prefix="/api/discord",
    tags=[DISCORD_TAG],
    dependencies=[Depends(require_session)],
    responses=PROTECTED_ROUTER_RESPONSES,
)


@router.get("/settings", **READ_DISCORD_SETTINGS_DOCS)
async def read_discord_settings(services: ServicesDep) -> dict[str, Any]:
    return build_ok_response(await services.scraper.read_discord_settings())


@router.put("/settings", **SAVE_DISCORD_SETTINGS_DOCS)
async def save_discord_settings(
    body: DiscordSettingsRequest, services: ServicesDep
) -> dict[str, Any]:
    return build_ok_response(await services.scraper.save_discord_settings(body.to_patch()))


@router.post("/test", **TEST_DISCORD_DOCS)
async def test_connection(services: ServicesDep) -> dict[str, Any]:
    return build_ok_response(await services.scraper.test_discord_connection())


@router.get("/channels", **READ_DISCORD_CHANNELS_DOCS)
async def read_channels(services: ServicesDep) -> dict[str, Any]:
    return build_ok_response({"channels": await services.scraper.list_discord_channels()})


@router.post("/preview", **PREVIEW_DISCORD_MESSAGE_DOCS)
async def preview_message(body: DiscordMessageRequest, services: ServicesDep) -> dict[str, Any]:
    messages = await services.scraper.preview_discord_message(body.mention, body.text, None)
    return build_ok_response({"messages": messages})


@router.post("/send", **SEND_DISCORD_MESSAGE_DOCS)
async def send_message(body: DiscordSendRequest, services: ServicesDep) -> dict[str, Any]:
    discord_delivery = await services.scraper.send_discord_message(
        body.channel_id, body.mention, body.text, None
    )
    return build_ok_response(discord_delivery)
