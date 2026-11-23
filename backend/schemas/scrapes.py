from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.schemas.config import Keyword, SiteName
from scraper.api.location_search_plan import (
    build_unknown_location_message,
    find_filter_location_option,
)
from scraper.config_loader import MAX_KEYWORDS
from scraper.max_age import build_unknown_max_age_message, is_max_age_option

MAX_SITES = 20
START_SCRAPE_EXAMPLE = {
    "keywords": ["data analyst"],
    "sites": ["linkedin", "jobstreet"],
    "notify_discord": False,
    "location": "Jakarta",
    "max_age_hours": 168,
}


class StartScrapeRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid", json_schema_extra={"examples": [START_SCRAPE_EXAMPLE]}
    )

    keywords: list[Keyword] = Field(
        min_length=1,
        max_length=MAX_KEYWORDS,
        description=f"Job titles to search, 1 to {MAX_KEYWORDS}",
    )
    sites: list[SiteName] = Field(
        min_length=1,
        max_length=MAX_SITES,
        description="Sites to search, names come from `GET /api/sites`",
    )
    notify_discord: bool = Field(
        default=False, description="Post the jobs to Discord when the scrape ends"
    )
    location: str | None = Field(
        default=None,
        description="One of `location_options` from `GET /api/config`, null searches all",
    )
    max_age_hours: int | None = Field(
        default=None,
        description="Skip jobs older than this, 72, 168 or 720, null uses each site setting",
    )

    @field_validator("location")
    @classmethod
    def pick_listed_location_option(cls, location: str | None) -> str | None:
        if location is None:
            return None
        location_option = find_filter_location_option(location)
        if location_option is None:
            raise ValueError(build_unknown_location_message(location))
        return location_option

    @field_validator("max_age_hours")
    @classmethod
    def check_listed_max_age_option(cls, max_age_hours: int | None) -> int | None:
        if max_age_hours is None:
            return None
        if not is_max_age_option(max_age_hours):
            raise ValueError(build_unknown_max_age_message(max_age_hours))
        return max_age_hours
