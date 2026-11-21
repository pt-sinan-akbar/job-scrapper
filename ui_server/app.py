from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import Scope

from ui_server.dependencies import Services, reject_cross_site
from ui_server.errors import install_error_handlers
from ui_server.routes import auth, config, discord, runs, sites
from ui_server.services.auth_service import AuthService
from ui_server.services.mcp_gateway import LocalGateway, McpGateway, ScraperClient
from ui_server.services.run_repository import RunRepository, open_run_repository
from ui_server.services.run_service import RunService
from ui_server.settings import Settings

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
ROUTE_MODULES = (auth, sites, runs, config, discord)
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
    run_repository: RunRepository | None = None,
) -> FastAPI:
    resolved_settings = _resolve_settings(settings)
    resolved_repository = _resolve_run_repository(run_repository)
    resolved_gateway = _resolve_gateway(gateway)
    services = _build_services(resolved_settings, resolved_gateway, resolved_repository)

    app = _create_fastapi(resolved_settings)
    app.state.services = services
    _add_trusted_host_middleware(app, resolved_settings)
    install_error_handlers(app)
    _register_routes(app)
    _mount_static_ui(app, resolved_settings)
    return app


def health() -> dict[str, str]:
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


def _resolve_settings(settings: Settings | None) -> Settings:
    if settings is None:
        return Settings()
    return settings


def _resolve_run_repository(run_repository: RunRepository | None) -> RunRepository:
    if run_repository is None:
        return open_run_repository()
    return run_repository


def _resolve_gateway(gateway: McpGateway | None) -> McpGateway:
    if gateway is None:
        return LocalGateway()
    return gateway


def _build_services(settings: Settings, gateway: McpGateway, repository: RunRepository) -> Services:
    scraper = ScraperClient(gateway)
    return Services(
        settings=settings,
        scraper=scraper,
        run_service=RunService(scraper, repository),
        auth=AuthService(settings),
    )


def _create_fastapi(settings: Settings) -> FastAPI:
    return FastAPI(
        title=APP_TITLE,
        dependencies=[Depends(reject_cross_site)],
        docs_url=_path_unless_prod(settings, DOCS_PATH),
        redoc_url=None,
        openapi_url=_path_unless_prod(settings, OPENAPI_PATH),
    )


def _path_unless_prod(settings: Settings, path: str) -> str | None:
    if settings.env == PROD_ENV:
        return None
    return path


def _add_trusted_host_middleware(app: FastAPI, settings: Settings) -> None:
    allowed_hosts = list(settings.allowed_hosts)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)


def _register_routes(app: FastAPI) -> None:
    app.get(HEALTH_PATH)(health)
    for module in ROUTE_MODULES:
        app.include_router(module.router)


def _mount_static_ui(app: FastAPI, settings: Settings) -> None:
    if not settings.static_dir.exists():
        return
    static_files = SpaStaticFiles(directory=settings.static_dir, html=True)
    app.mount(UI_MOUNT_PATH, static_files, name=UI_MOUNT_NAME)


def _should_fall_back_to_index(exc: HTTPException, path: str) -> bool:
    if exc.status_code != NOT_FOUND_STATUS:
        return False
    return not path.startswith(API_PREFIX)
