from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.schemas.config import Keyword, SiteName
from scraper.api.location_search_plan import (
    build_unknown_location_message,
    find_filter_location_option,
)
from scraper.max_age import build_unknown_max_age_message, is_max_age_option

MAX_KEYWORDS = 20
MAX_SITES = 20


class StartScrapeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keywords: list[Keyword] = Field(min_length=1, max_length=MAX_KEYWORDS)
    sites: list[SiteName] = Field(min_length=1, max_length=MAX_SITES)
    notify_discord: bool = False
    location: str | None = None
    max_age_hours: int | None = None

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
