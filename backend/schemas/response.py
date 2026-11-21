from __future__ import annotations

from typing import Any


def build_ok_response(payload: Any, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    response_body: dict[str, Any] = {"success": True, "data": payload, "error": None}
    if meta is None:
        return response_body
    return {**response_body, "meta": meta}


def build_failure_response(error: Any) -> dict[str, Any]:
    return {"success": False, "data": None, "error": error}
