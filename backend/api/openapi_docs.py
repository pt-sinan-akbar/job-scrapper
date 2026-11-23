from __future__ import annotations

from typing import Any

from backend.errors import (
    ConfigConflictError,
    DiscordForbiddenError,
    DiscordNotConfiguredError,
    DiscordUnauthorizedError,
    InvalidPasswordError,
    McpUnavailableError,
    NotSignedInError,
    ScrapeInProgressError,
    ScrapeNotFoundError,
    ScrapeNotSendableError,
    ScrapeStorageUnavailableError,
    TooManyAttemptsError,
)
from backend.schemas.response import build_failure_response, build_ok_response
from backend.services.auth_service import FAILURE_WINDOW_SECONDS, MAX_FAILED_ATTEMPTS

JSON_MEDIA_TYPE = "application/json"
SECONDS_PER_MINUTE = 60


def build_success_response(description: str, example_payload: Any) -> dict[str, Any]:
    return _build_json_response(description, build_ok_response(example_payload))


def build_error_response(description: str, error_message: Any) -> dict[str, Any]:
    return _build_json_response(description, build_failure_response(error_message))


def build_invalid_body_response(example_errors: dict[str, list[str]]) -> dict[str, Any]:
    return build_error_response("Body is not valid, errors are listed per field", example_errors)


def _build_json_response(description: str, example_body: dict[str, Any]) -> dict[str, Any]:
    return {"description": description, "content": {JSON_MEDIA_TYPE: {"example": example_body}}}


AUTH_TAG = "Auth"
SCRAPES_TAG = "Scrapes"
SITES_TAG = "Sites"
CONFIG_TAG = "Config"
DISCORD_TAG = "Discord"
HEALTH_TAG = "Health"

OPENAPI_TAGS = [
    {"name": AUTH_TAG, "description": "Log in, log out and check the UI session"},
    {"name": SCRAPES_TAG, "description": "Start scrapes and read their reports"},
    {"name": SITES_TAG, "description": "List the job sites the scraper supports"},
    {"name": CONFIG_TAG, "description": "Read and save the scraper job settings"},
    {"name": DISCORD_TAG, "description": "Discord channel settings and sending scrape results"},
    {"name": HEALTH_TAG, "description": "Liveness check for the service"},
]

API_DESCRIPTION = (
    "API behind the scraper UI\n\n"
    "- Every `/api` route except `/api/auth/*` needs a login: log in with "
    "`POST /api/auth/login`, or send `Authorization: Bearer <AUTH_TOKEN>`\n"
    "- Every response has the same shape: `{success, data, error}`"
)

SCRAPE_ID_EXAMPLE = "20261122T113251Z-6860e9"

STARTED_SCRAPE_EXAMPLE = {
    "id": SCRAPE_ID_EXAMPLE,
    "status": "running",
    "keywords": ["data analyst"],
    "sites": ["linkedin", "jobstreet"],
    "started_at": "2026-11-22T11:32:51+00:00",
    "location": "Jakarta",
    "max_age_hours": 168,
    "finished_at": None,
    "job_count": 0,
    "error_count": 0,
    "error": None,
    "discord_status": None,
    "discord_sent": 0,
    "discord_failed": 0,
    "discord_error": None,
}

FINISHED_SCRAPE_EXAMPLE = {
    **STARTED_SCRAPE_EXAMPLE,
    "status": "partial",
    "finished_at": "2026-11-22T11:33:07+00:00",
    "job_count": 1,
    "error_count": 1,
}

SENDING_SCRAPE_EXAMPLE = {**FINISHED_SCRAPE_EXAMPLE, "discord_status": "sending"}

SCRAPE_REPORT_EXAMPLE = {
    "record": FINISHED_SCRAPE_EXAMPLE,
    "jobs": [
        {
            "site": "jobstreet",
            "matched_keyword": "data analyst",
            "title": "Data Analyst",
            "company": "PT Contoh Indonesia",
            "location": "Jakarta Selatan",
            "url": "https://id.jobstreet.com/id/job/12345678",
            "posted_at": "2026-11-21T08:00:00+00:00",
            "salary": "IDR 8,000,000 - 12,000,000 per month",
            "work_type": "hybrid",
            "employment_type": "full_time",
        }
    ],
    "failures": [{"keyword": "data analyst", "site": "linkedin", "reason": "fetch failed"}],
}

DISCORD_SETTINGS_EXAMPLE = {
    "configured": True,
    "token_hint": "••••ObKI",
    "default_channel_id": "1168534153994698885",
    "mention_user_id": None,
    "message_template": "# {title}\n**{company}** · {location}",
    "max_chars": 1900,
    "updated_at": "2026-11-21T12:08:10+00:00",
}

NOT_SIGNED_IN_RESPONSE = build_error_response("Not logged in", NotSignedInError.default_message)
SCRAPER_DOWN_RESPONSE = build_error_response(
    "Scraper service is down", McpUnavailableError.default_message
)
DISCORD_NOT_CONFIGURED_RESPONSE = build_error_response(
    "Discord bot token is not set", DiscordNotConfiguredError.default_message
)


PROTECTED_ROUTER_RESPONSES: dict[int | str, dict[str, Any]] = {401: NOT_SIGNED_IN_RESPONSE}

READ_SESSION_DOCS: dict[str, Any] = {
    "summary": "Check login status",
    "description": "Tells you if this browser is logged in",
    "responses": {
        200: build_success_response("Login status", {"auth_required": True, "signed_in": False})
    },
}

LOGIN_DOCS: dict[str, Any] = {
    "summary": "Log in",
    "description": (
        "Checks the password and sets the session cookie, "
        f"{MAX_FAILED_ATTEMPTS} wrong tries in "
        f"{int(FAILURE_WINDOW_SECONDS // SECONDS_PER_MINUTE)} minutes blocks you for a while"
    ),
    "responses": {
        200: build_success_response("Logged in, session cookie set", None),
        401: build_error_response("Wrong password", InvalidPasswordError.default_message),
        422: build_invalid_body_response({"password": ["Field required"]}),
        429: build_error_response("Too many wrong tries", TooManyAttemptsError.default_message),
    },
}

LOGOUT_DOCS: dict[str, Any] = {
    "summary": "Log out",
    "description": "Removes the session cookie",
    "responses": {200: build_success_response("Logged out", None)},
}

READ_SITES_DOCS: dict[str, Any] = {
    "summary": "List sites",
    "description": (
        "Lists every job site and whether it is turned on, "
        "`is_stale` is true when the scraper is down and this is the last copy it sent"
    ),
    "responses": {
        200: build_success_response(
            "Sites",
            {
                "sites": [
                    {"name": "jobstreet", "enabled": True},
                    {"name": "glints", "enabled": False},
                ],
                "is_stale": False,
            },
        ),
        503: SCRAPER_DOWN_RESPONSE,
    },
}

READ_CONFIG_DOCS: dict[str, Any] = {
    "summary": "Read job settings",
    "description": (
        "Returns the saved settings, plus the choices the UI needs: "
        "job fields, locations and max age options, keep `version` because saving needs it"
    ),
    "responses": {
        200: build_success_response(
            "Job settings",
            {
                "values": {
                    "fields": ["title", "company"],
                    "sites": [
                        {
                            "name": "jobstreet",
                            "enabled": True,
                            "limit": 5,
                            "max_age_hours": 72,
                            "filter": {"location": ["jakarta"]},
                            "api": {"enabled": True, "delay_seconds": [2.0, 4.0]},
                            "url_template": "https://id.jobstreet.com/id/{keyword_slug}-jobs",
                        }
                    ],
                },
                "version": 18,
                "updated_at": "2026-11-22T05:17:16+00:00",
                "updated_by": "ui",
                "is_stale": False,
                "job_fields": ["site", "matched_keyword", "title", "company"],
                "mandatory_fields": ["site", "matched_keyword"],
                "location_options": ["Jakarta", "Tangerang"],
                "max_age_options": [{"value": 72, "label": "3 days ago"}],
            },
        ),
        503: SCRAPER_DOWN_RESPONSE,
    },
}

SAVE_CONFIG_DOCS: dict[str, Any] = {
    "summary": "Save job settings",
    "description": (
        "Changes only the keys you send, `version` must match the one from "
        "`GET /api/config`, otherwise you get 409 and need to read again"
    ),
    "responses": {
        200: build_success_response("Saved", None),
        409: build_error_response(
            "Settings changed since you read them", ConfigConflictError.default_message
        ),
        422: build_invalid_body_response(
            {"sites.jobstreet.limit": ["Input should be less than or equal to 200"]}
        ),
        503: SCRAPER_DOWN_RESPONSE,
    },
}

START_SCRAPE_DOCS: dict[str, Any] = {
    "summary": "Start a scrape",
    "description": (
        "Starts a scrape in the background and answers right away with its id\n\n"
        "- Follow it with `GET /api/scrapes/{scrape_id}`\n"
        "- Only one scrape runs at a time"
    ),
    "responses": {
        202: build_success_response("Scrape started", STARTED_SCRAPE_EXAMPLE),
        409: build_error_response(
            "A scrape is already running", ScrapeInProgressError.default_message
        ),
        422: build_error_response("Unknown site", "Unknown site: glassdoor"),
        503: SCRAPER_DOWN_RESPONSE,
    },
}

SEND_LATEST_SCRAPE_DOCS: dict[str, Any] = {
    "summary": "Send latest scrape to Discord",
    "description": (
        "Posts the jobs of the latest finished scrape to the default Discord channel "
        "in the background, follow `discord_status` on the scrape"
    ),
    "responses": {
        202: build_success_response("Sending started", SENDING_SCRAPE_EXAMPLE),
        404: build_error_response("No scrape yet", ScrapeNotFoundError.default_message),
        409: build_error_response(
            "Latest scrape is still running or failed", ScrapeNotSendableError.default_message
        ),
    },
}

READ_LATEST_SCRAPE_DOCS: dict[str, Any] = {
    "summary": "Read latest scrape",
    "description": (
        "Returns the newest scrape with its jobs and failures, "
        "`data` is null when there is no scrape yet"
    ),
    "responses": {200: build_success_response("Latest scrape", SCRAPE_REPORT_EXAMPLE)},
}

READ_SCRAPE_DOCS: dict[str, Any] = {
    "summary": "Read a scrape",
    "description": "Returns one scrape with its jobs and failures",
    "responses": {
        200: build_success_response("Scrape", SCRAPE_REPORT_EXAMPLE),
        404: build_error_response("No scrape with this id", ScrapeNotFoundError.default_message),
        503: build_error_response(
            "Scrape storage is down", ScrapeStorageUnavailableError.default_message
        ),
    },
}

READ_DISCORD_SETTINGS_DOCS: dict[str, Any] = {
    "summary": "Read Discord settings",
    "description": "The bot token is never returned, only its last 4 characters in `token_hint`",
    "responses": {
        200: build_success_response("Discord settings", DISCORD_SETTINGS_EXAMPLE),
        503: SCRAPER_DOWN_RESPONSE,
    },
}

SAVE_DISCORD_SETTINGS_DOCS: dict[str, Any] = {
    "summary": "Save Discord settings",
    "description": (
        "Changes only the keys you send, "
        "send an empty string to clear `default_channel_id` or `mention_user_id`"
    ),
    "responses": {
        200: build_success_response("Saved settings", DISCORD_SETTINGS_EXAMPLE),
        422: build_invalid_body_response(
            {"max_chars": ["Input should be less than or equal to 2000"]}
        ),
        503: SCRAPER_DOWN_RESPONSE,
    },
}

TEST_DISCORD_DOCS: dict[str, Any] = {
    "summary": "Test the bot token",
    "description": "Logs in to Discord with the saved token and returns the bot name",
    "responses": {
        200: build_success_response(
            "Token works", {"bot_name": "job-bot", "bot_id": "1168534153994698000"}
        ),
        409: DISCORD_NOT_CONFIGURED_RESPONSE,
        422: build_error_response(
            "Discord refused the token", DiscordUnauthorizedError.default_message
        ),
        503: SCRAPER_DOWN_RESPONSE,
    },
}

READ_DISCORD_CHANNELS_DOCS: dict[str, Any] = {
    "summary": "List channels",
    "description": "Lists the channels the bot can post in, with their server",
    "responses": {
        200: build_success_response(
            "Channels",
            {
                "channels": [
                    {
                        "id": "902835123869864051",
                        "name": "general",
                        "guild_id": "902835123869864047",
                        "guild_name": "My server",
                    }
                ]
            },
        ),
        409: DISCORD_NOT_CONFIGURED_RESPONSE,
        503: SCRAPER_DOWN_RESPONSE,
    },
}

PREVIEW_DISCORD_MESSAGE_DOCS: dict[str, Any] = {
    "summary": "Preview a message",
    "description": "Shows how the text is split into Discord messages, nothing is sent",
    "responses": {
        200: build_success_response("Messages as they would be sent", {"messages": ["Hello team"]}),
        422: build_invalid_body_response({"text": ["Field required"]}),
        503: SCRAPER_DOWN_RESPONSE,
    },
}

SEND_DISCORD_MESSAGE_DOCS: dict[str, Any] = {
    "summary": "Send a message",
    "description": "Sends the text to a channel, `sent` and `failed` count Discord messages",
    "responses": {
        200: build_success_response(
            "Send result",
            {
                "sent": 1,
                "failed": 0,
                "results": [
                    {
                        "index": 0,
                        "kind": "text",
                        "title": None,
                        "job_count": 0,
                        "status": "sent",
                        "message_id": "1170000000000000000",
                        "error": None,
                    }
                ],
            },
        ),
        409: DISCORD_NOT_CONFIGURED_RESPONSE,
        422: build_error_response(
            "Bot can't post in that channel", DiscordForbiddenError.default_message
        ),
        503: SCRAPER_DOWN_RESPONSE,
    },
}

READ_HEALTH_DOCS: dict[str, Any] = {
    "summary": "Health check",
    "description": "Returns ok when the service is up, no login needed",
    "responses": {200: _build_json_response("Service is up", {"status": "ok"})},
}
