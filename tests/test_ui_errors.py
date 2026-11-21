from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from backend.errors import ScrapeInProgressError, install_error_handlers
from backend.schemas.response import build_ok_response


class Body(BaseModel):
    limit: int


def _client() -> TestClient:
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/busy")
    def busy() -> None:
        raise ScrapeInProgressError()

    @app.get("/crash")
    def crash() -> None:
        raise RuntimeError("secret detail")

    @app.post("/validate")
    def validate(body: Body) -> dict:
        return build_ok_response(body.limit)

    return TestClient(app, raise_server_exceptions=False)


def test_ok_wraps_data():
    assert build_ok_response({"a": 1}) == {"success": True, "data": {"a": 1}, "error": None}


def test_ok_adds_meta_when_given():
    assert build_ok_response([], meta={"total": 0})["meta"] == {"total": 0}


def test_app_error_uses_error_envelope():
    response = _client().get("/busy")

    assert response.status_code == 409
    assert response.json() == {
        "success": False,
        "data": None,
        "error": "A scrape is already running.",
    }


def test_validation_error_lists_fields():
    response = _client().post("/validate", json={"limit": "x"})

    assert response.status_code == 422
    assert list(response.json()["error"]) == ["limit"]


def test_unexpected_error_hides_the_error_text():
    response = _client().get("/crash")

    assert response.status_code == 500
    assert "secret detail" not in response.text
