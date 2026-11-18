from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, status

from ui_server.dependencies import ServicesDep, require_session
from ui_server.errors import ConfigInvalidError
from ui_server.schema.response import ok
from ui_server.schema.runs import StartRunRequest
from ui_server.services.run_detail import detail_to_dict, record_to_dict

router = APIRouter(prefix="/api/runs", dependencies=[Depends(require_session)])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def start_run(body: StartRunRequest, services: ServicesDep) -> dict[str, Any]:
    services.run_service.ensure_idle()
    read = await services.scraper.read_sites()
    known = {site["name"] for site in read.value.get("sites", [])}
    unknown = sorted(set(body.sites) - known)
    if unknown:
        raise ConfigInvalidError(f"Unknown site: {', '.join(unknown)}")
    record = services.run_service.start(
        tuple(body.keywords), tuple(body.sites), body.notify_discord
    )
    return ok(record_to_dict(record))


@router.get("/latest")
def read_latest_run(services: ServicesDep) -> dict[str, Any]:
    detail = services.run_service.latest()
    return ok(None if detail is None else detail_to_dict(detail))


@router.get("/{run_id}")
def read_run(run_id: str, services: ServicesDep) -> dict[str, Any]:
    return ok(detail_to_dict(services.run_service.get(run_id)))
