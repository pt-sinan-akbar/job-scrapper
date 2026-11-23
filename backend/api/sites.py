from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from backend.api.openapi_docs import PROTECTED_ROUTER_RESPONSES, READ_SITES_DOCS, SITES_TAG
from backend.dependencies import ServicesDep, require_session
from backend.schemas.response import build_ok_response

router = APIRouter(
    prefix="/api/sites",
    tags=[SITES_TAG],
    dependencies=[Depends(require_session)],
    responses=PROTECTED_ROUTER_RESPONSES,
)


@router.get("", **READ_SITES_DOCS)
async def read_sites(services: ServicesDep) -> dict[str, Any]:
    sites_read = await services.scraper.read_sites()
    return build_ok_response(
        {
            "sites": _build_site_entries(sites_read.tool_response),
            "is_stale": sites_read.is_stale,
        }
    )


def _build_site_entries(sites_response: dict[str, Any]) -> list[dict[str, Any]]:
    site_entries: list[dict[str, Any]] = []
    for site in sites_response.get("sites", []):
        site_entries.append({"name": site["name"], "enabled": site["enabled"]})
    return site_entries
