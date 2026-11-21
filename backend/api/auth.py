from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response

from backend.dependencies import ServicesDep
from backend.schemas.auth import LoginRequest
from backend.schemas.response import build_ok_response
from backend.services.auth_service import SESSION_COOKIE, SESSION_MAX_AGE_SECONDS

UNKNOWN_CLIENT = "unknown"

router = APIRouter(prefix="/api/auth")


@router.get("/session")
def read_session(request: Request, services: ServicesDep) -> dict[str, Any]:
    signed_in = services.auth.is_signed_in(request.cookies.get(SESSION_COOKIE))
    return build_ok_response({"auth_required": True, "signed_in": signed_in})


@router.post("/login")
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    services: ServicesDep,
) -> dict[str, Any]:
    client = request.client.host if request.client else UNKNOWN_CLIENT
    token = services.auth.login(body.password, client)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=services.settings.cookie_secure,
        samesite="strict",
    )
    return build_ok_response(None)


@router.post("/logout")
def logout(response: Response, services: ServicesDep) -> dict[str, Any]:
    response.delete_cookie(
        SESSION_COOKIE,
        httponly=True,
        secure=services.settings.cookie_secure,
        samesite="strict",
    )
    return build_ok_response(None)
