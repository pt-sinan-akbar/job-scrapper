from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from backend.api.openapi_docs import (
    CONFIG_TAG,
    PROTECTED_ROUTER_RESPONSES,
    READ_CONFIG_DOCS,
    SAVE_CONFIG_DOCS,
)
from backend.dependencies import ServicesDep, require_session
from backend.schemas.config import ConfigUpdateRequest
from backend.schemas.response import build_ok_response

REMOVED_API_KEYS: frozenset[str] = frozenset({"locations", "country_wide"})

router = APIRouter(
    prefix="/api/config",
    tags=[CONFIG_TAG],
    dependencies=[Depends(require_session)],
    responses=PROTECTED_ROUTER_RESPONSES,
)


@router.get("", **READ_CONFIG_DOCS)
async def read_config(services: ServicesDep) -> dict[str, Any]:
    config_read = await services.scraper.read_config()
    return build_ok_response(
        {
            "values": _build_config_values(config_read.tool_response["settings"]),
            "version": config_read.tool_response["version"],
            "updated_at": config_read.tool_response["updated_at"],
            "updated_by": config_read.tool_response["updated_by"],
            "is_stale": config_read.is_stale,
            "job_fields": config_read.tool_response.get("job_fields", []),
            "mandatory_fields": config_read.tool_response.get("mandatory_fields", []),
            "location_options": config_read.tool_response.get("location_options", []),
            "max_age_options": config_read.tool_response.get("max_age_options", []),
        }
    )


@router.put("", **SAVE_CONFIG_DOCS)
async def save_config(body: ConfigUpdateRequest, services: ServicesDep) -> dict[str, Any]:
    await services.scraper.save_config(body.to_patch(), body.version)
    return build_ok_response(None)


def _build_config_values(settings: dict[str, Any]) -> dict[str, Any]:
    site_responses = []
    for name, site in settings.get("sites", {}).items():
        site_responses.append(_build_site_response(name, site))
    return {
        "fields": settings.get("fields", []),
        "sites": site_responses,
    }


def _build_site_response(name: str, site: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "enabled": site.get("enabled", True),
        "limit": site.get("limit"),
        "max_age_hours": site.get("max_age_hours"),
        "filter": _build_filter_response(site.get("filter")),
        "api": _build_api_response(site.get("api")),
        "url_template": site.get("url_template"),
    }


def _build_api_response(api_settings: dict[str, Any] | None) -> dict[str, Any] | None:
    if api_settings is None:
        return None
    api_response: dict[str, Any] = {}
    for api_key, api_value in api_settings.items():
        if api_key in REMOVED_API_KEYS:
            continue
        api_response[api_key] = api_value
    return api_response


def _build_filter_response(raw_filter: dict[str, Any] | None) -> dict[str, list[str]]:
    if raw_filter is None:
        return {}
    filter_response = {}
    for filter_key, filter_values in raw_filter.items():
        if not filter_values:
            continue
        if isinstance(filter_values, str):
            filter_response[filter_key] = [filter_values]
            continue
        filter_response[filter_key] = filter_values
    return filter_response
