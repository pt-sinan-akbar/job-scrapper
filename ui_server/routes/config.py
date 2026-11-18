from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ui_server.dependencies import ServicesDep, require_session
from ui_server.schema.config import ConfigUpdateRequest
from ui_server.schema.response import ok

router = APIRouter(prefix="/api/config", dependencies=[Depends(require_session)])


def _to_filter(raw: dict[str, Any] | None) -> dict[str, list[str]]:
    if raw is None:
        return {}
    return {
        key: [value] if isinstance(value, str) else value for key, value in raw.items() if value
    }


def _to_site(name: str, site: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "enabled": site.get("enabled", True),
        "limit": site.get("limit"),
        "max_age_hours": site.get("max_age_hours"),
        "filter": _to_filter(site.get("filter")),
        "fields": site.get("fields"),
        "api": site.get("api"),
    }


def _to_values(settings: dict[str, Any]) -> dict[str, Any]:
    return {
        "default_fields": settings.get("default_fields", []),
        "sites": [_to_site(name, site) for name, site in settings.get("sites", {}).items()],
    }


@router.get("")
async def read_config(services: ServicesDep) -> dict[str, Any]:
    read = await services.scraper.read_config()
    return ok(
        {
            "values": _to_values(read.value["settings"]),
            "version": read.value["version"],
            "updated_at": read.value["updated_at"],
            "updated_by": read.value["updated_by"],
            "is_stale": read.is_stale,
            "job_fields": read.value.get("job_fields", []),
            "mandatory_fields": read.value.get("mandatory_fields", []),
            "location_options": read.value.get("location_options", {}),
        }
    )


@router.put("")
async def update_config(body: ConfigUpdateRequest, services: ServicesDep) -> dict[str, Any]:
    await services.scraper.save_config(body.to_patch(), body.version)
    return ok(None)
