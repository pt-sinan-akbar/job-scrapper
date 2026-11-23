from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, status

from backend.api.openapi_docs import (
    PROTECTED_ROUTER_RESPONSES,
    READ_LATEST_SCRAPE_DOCS,
    READ_SCRAPE_DOCS,
    SCRAPE_ID_EXAMPLE,
    SCRAPES_TAG,
    SEND_LATEST_SCRAPE_DOCS,
    START_SCRAPE_DOCS,
)
from backend.dependencies import ServicesDep, require_session
from backend.errors import ConfigInvalidError
from backend.schemas.response import build_ok_response
from backend.schemas.scrapes import StartScrapeRequest
from backend.services.scrape_report import build_report_response, convert_summary_to_dict

router = APIRouter(
    prefix="/api/scrapes",
    tags=[SCRAPES_TAG],
    dependencies=[Depends(require_session)],
    responses=PROTECTED_ROUTER_RESPONSES,
)

ScrapeId = Annotated[
    str, Path(description="Scrape id from `POST /api/scrapes`", examples=[SCRAPE_ID_EXAMPLE])
]


@router.post("", status_code=status.HTTP_202_ACCEPTED, **START_SCRAPE_DOCS)
async def start_scrape(body: StartScrapeRequest, services: ServicesDep) -> dict[str, Any]:
    services.scrape_service.ensure_idle()
    sites_read = await services.scraper.read_sites()
    known_site_names = _list_known_site_names(sites_read.tool_response)
    unknown_site_names = sorted(set(body.sites) - known_site_names)
    if unknown_site_names:
        raise ConfigInvalidError(f"Unknown site: {', '.join(unknown_site_names)}")
    scrape_summary = services.scrape_service.start_scrape(
        tuple(body.keywords),
        tuple(body.sites),
        body.notify_discord,
        body.location,
        body.max_age_hours,
    )
    return build_ok_response(convert_summary_to_dict(scrape_summary))


@router.post("/latest/discord", status_code=status.HTTP_202_ACCEPTED, **SEND_LATEST_SCRAPE_DOCS)
async def send_latest_scrape_to_discord(services: ServicesDep) -> dict[str, Any]:
    scrape_summary = await services.scrape_service.send_latest_scrape_to_discord()
    return build_ok_response(convert_summary_to_dict(scrape_summary))


@router.get("/latest", **READ_LATEST_SCRAPE_DOCS)
def read_latest_scrape_report(services: ServicesDep) -> dict[str, Any]:
    latest_report = services.scrape_service.read_latest_scrape_report()
    if latest_report is None:
        return build_ok_response(None)
    return build_ok_response(build_report_response(latest_report))


@router.get("/{scrape_id}", **READ_SCRAPE_DOCS)
def read_scrape_report(scrape_id: ScrapeId, services: ServicesDep) -> dict[str, Any]:
    scrape_report = services.scrape_service.read_scrape_report(scrape_id)
    return build_ok_response(build_report_response(scrape_report))


def _list_known_site_names(sites_response: dict[str, Any]) -> set[str]:
    known_site_names: set[str] = set()
    for site in sites_response.get("sites", []):
        known_site_names.add(site["name"])
    return known_site_names
