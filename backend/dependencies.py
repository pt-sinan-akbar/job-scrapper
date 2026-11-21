from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from backend.errors import CrossSiteRequestError, NotSignedInError
from backend.services.auth_service import SESSION_COOKIE, AuthService
from backend.services.scrape_service import ScrapeService
from backend.services.scraper_client import ScraperClient
from backend.settings import Settings

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
ALLOWED_FETCH_SITES = frozenset({"same-origin", "none"})


@dataclass(frozen=True)
class Services:
    settings: Settings
    scraper: ScraperClient
    scrape_service: ScrapeService
    auth: AuthService


def get_services(request: Request) -> Services:
    return request.app.state.services


ServicesDep = Annotated[Services, Depends(get_services)]


def require_session(request: Request, services: ServicesDep) -> None:
    if not services.auth.is_signed_in(request.cookies.get(SESSION_COOKIE)):
        raise NotSignedInError()


def reject_cross_site(request: Request) -> None:
    if request.method in SAFE_METHODS:
        return
    fetch_site = request.headers.get("sec-fetch-site")
    if fetch_site is not None and fetch_site not in ALLOWED_FETCH_SITES:
        raise CrossSiteRequestError()
