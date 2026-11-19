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


class SpaStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Any:
        response = await self._find_response(path, scope)
        response.headers.update(SECURITY_HEADERS)
        return response

    async def _find_response(self, path: str, scope: Scope) -> Any:
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != NOT_FOUND_STATUS or path.startswith(API_PREFIX):
                raise
            return await super().get_response(INDEX_FILE, scope)


def _build_services(settings: Settings, gateway: McpGateway, repository: RunRepository) -> Services:
    scraper = ScraperClient(gateway)
    return Services(
        settings=settings,
        scraper=scraper,
        run_service=RunService(scraper, repository),
        auth=AuthService(settings),
    )


def create_app(
    settings: Settings | None = None,
    gateway: McpGateway | None = None,
    run_repository: RunRepository | None = None,
) -> FastAPI:
    resolved = settings or Settings()
    repository = run_repository or open_run_repository()
    services = _build_services(resolved, gateway or LocalGateway(), repository)

    app = FastAPI(
        title="Scraper UI",
        dependencies=[Depends(reject_cross_site)],
        docs_url=None if resolved.env == "prod" else "/docs",
        redoc_url=None,
        openapi_url=None if resolved.env == "prod" else "/openapi.json",
    )
    app.state.services = services
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(resolved.allowed_hosts))
    install_error_handlers(app)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    for module in (auth, sites, runs, config, discord):
        app.include_router(module.router)
    if resolved.static_dir.exists():
        app.mount("/", SpaStaticFiles(directory=resolved.static_dir, html=True), name="ui")
    return app
