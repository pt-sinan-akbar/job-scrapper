from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import Scope

from backend.api import auth, config, discord, scrapes, sites
from backend.api.openapi_docs import (
    API_DESCRIPTION,
    HEALTH_TAG,
    OPENAPI_TAGS,
    READ_HEALTH_DOCS,
)
from backend.dependencies import Services, reject_cross_site
from backend.errors import install_error_handlers
from backend.services.auth_service import AuthService
from backend.services.scrape_report_repository import (
    ScrapeReportRepository,
    open_scrape_report_repository,
)
from backend.services.scrape_service import ScrapeService
from backend.services.scraper_client import LocalGateway, McpGateway, ScraperClient
from backend.settings import Settings

NOT_FOUND_STATUS = 404
API_PREFIX = "api"
INDEX_FILE = "index.html"
PROD_ENV = "prod"
APP_TITLE = "Scraper UI"
DOCS_PATH = "/docs"
OPENAPI_PATH = "/openapi.json"
HEALTH_PATH = "/health"
HEALTH_STATUS_OK = "ok"
UI_MOUNT_PATH = "/"
UI_MOUNT_NAME = "ui"
API_ROUTER_MODULES = (auth, sites, scrapes, config, discord)
CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src 'self' https://fonts.gstatic.com",
        "img-src 'self' data:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    )
)
SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
}


def create_app(
    settings: Settings | None = None,
    gateway: McpGateway | None = None,
    scrape_report_repository: ScrapeReportRepository | None = None,
) -> FastAPI:
    app_settings = _pick_settings(settings)
    app_scrape_report_repository = _pick_scrape_report_repository(scrape_report_repository)
    app_gateway = _pick_gateway(gateway)
    services = _build_services(app_settings, app_gateway, app_scrape_report_repository)

    app = _create_fastapi_app(app_settings)
    app.state.services = services
    _add_trusted_host_middleware(app, app_settings)
    install_error_handlers(app)
    _register_api_routers(app)
    _mount_static_ui(app, app_settings)
    return app


def read_health() -> dict[str, str]:
    return {"status": HEALTH_STATUS_OK}


class SpaStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Any:
        response = await self._find_response(path, scope)
        response.headers.update(SECURITY_HEADERS)
        return response

    async def _find_response(self, path: str, scope: Scope) -> Any:
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if not _should_fall_back_to_index(exc, path):
                raise
            return await super().get_response(INDEX_FILE, scope)


def _pick_settings(settings: Settings | None) -> Settings:
    if settings is None:
        return Settings()
    return settings


def _pick_scrape_report_repository(
    scrape_report_repository: ScrapeReportRepository | None,
) -> ScrapeReportRepository:
    if scrape_report_repository is None:
        return open_scrape_report_repository()
    return scrape_report_repository


def _pick_gateway(gateway: McpGateway | None) -> McpGateway:
    if gateway is None:
        return LocalGateway()
    return gateway


def _build_services(
    settings: Settings, gateway: McpGateway, repository: ScrapeReportRepository
) -> Services:
    scraper = ScraperClient(gateway)
    return Services(
        settings=settings,
        scraper=scraper,
        scrape_service=ScrapeService(scraper, repository),
        auth=AuthService(settings),
    )


def _create_fastapi_app(settings: Settings) -> FastAPI:
    return FastAPI(
        title=APP_TITLE,
        description=API_DESCRIPTION,
        openapi_tags=OPENAPI_TAGS,
        dependencies=[Depends(reject_cross_site)],
        docs_url=_hide_path_in_prod(settings, DOCS_PATH),
        redoc_url=None,
        openapi_url=_hide_path_in_prod(settings, OPENAPI_PATH),
    )


def _hide_path_in_prod(settings: Settings, path: str) -> str | None:
    if settings.env == PROD_ENV:
        return None
    return path


def _add_trusted_host_middleware(app: FastAPI, settings: Settings) -> None:
    allowed_hosts = list(settings.allowed_hosts)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)


def _register_api_routers(app: FastAPI) -> None:
    app.get(HEALTH_PATH, tags=[HEALTH_TAG], **READ_HEALTH_DOCS)(read_health)
    for api_module in API_ROUTER_MODULES:
        app.include_router(api_module.router)


def _mount_static_ui(app: FastAPI, settings: Settings) -> None:
    if not settings.static_dir.exists():
        return
    static_files = SpaStaticFiles(directory=settings.static_dir, html=True)
    app.mount(UI_MOUNT_PATH, static_files, name=UI_MOUNT_NAME)


def _should_fall_back_to_index(exc: HTTPException, path: str) -> bool:
    if exc.status_code != NOT_FOUND_STATUS:
        return False
    return not path.startswith(API_PREFIX)
