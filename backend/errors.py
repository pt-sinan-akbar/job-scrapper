from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.schemas.response import build_failure_response

LOG = logging.getLogger("scraper-ui")
UNEXPECTED_MESSAGE = "Something went wrong. Try again."


class AppError(Exception):
    status_code = 400
    default_message = "The request could not be completed."

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.default_message
        super().__init__(self.message)


class NotSignedInError(AppError):
    status_code = 401
    default_message = "You are not signed in."


class InvalidPasswordError(AppError):
    status_code = 401
    default_message = "Wrong password."


class CrossSiteRequestError(AppError):
    status_code = 403
    default_message = "Cross-site requests are not allowed."


class ConfigConflictError(AppError):
    status_code = 409
    default_message = "These settings changed somewhere else. Reload and try again."


class ScrapeNotFoundError(AppError):
    status_code = 404
    default_message = "Run not found."


class ScrapeStorageUnavailableError(AppError):
    status_code = 503
    default_message = "Run storage is unavailable."


class ScrapeInProgressError(AppError):
    status_code = 409
    default_message = "A scrape is already running."


class ScrapeNotSendableError(AppError):
    status_code = 409
    default_message = "Only a finished run can be sent to Discord."


class ConfigInvalidError(AppError):
    status_code = 422
    default_message = "That config is not valid."


class TooManyAttemptsError(AppError):
    status_code = 429
    default_message = "Too many tries. Try again in a few minutes."


class DiscordNotConfiguredError(AppError):
    status_code = 409
    default_message = "Set up Discord in Config first."


class DiscordUnauthorizedError(AppError):
    status_code = 422
    default_message = "Discord rejected the bot token."


class DiscordForbiddenError(AppError):
    status_code = 422
    default_message = "The bot can't post in that channel."


class McpUnavailableError(AppError):
    status_code = 503
    default_message = "The scraper service could not be reached."


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def respond_to_app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code, content=build_failure_response(exc.message)
        )

    @app.exception_handler(RequestValidationError)
    async def respond_to_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422, content=build_failure_response(_collect_field_errors(exc))
        )

    @app.exception_handler(Exception)
    async def respond_to_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        LOG.error("unhandled error on %s", request.url.path, exc_info=exc)
        return JSONResponse(status_code=500, content=build_failure_response(UNEXPECTED_MESSAGE))


def _collect_field_errors(exc: RequestValidationError) -> dict[str, list[str]]:
    field_errors: dict[str, list[str]] = {}
    for validation_error in exc.errors():
        field_name = _build_field_name(validation_error["loc"])
        field_messages = [*field_errors.get(field_name, []), validation_error["msg"]]
        field_errors = {**field_errors, field_name: field_messages}
    return field_errors


def _build_field_name(error_location: tuple[Any, ...]) -> str:
    field_path = ".".join(str(part) for part in error_location[1:])
    if not field_path:
        return "body"
    return field_path
