from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from backend.schemas.config import Keyword, SiteName

MAX_KEYWORDS = 20
MAX_SITES = 20


class StartScrapeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keywords: list[Keyword] = Field(min_length=1, max_length=MAX_KEYWORDS)
    sites: list[SiteName] = Field(min_length=1, max_length=MAX_SITES)
    notify_discord: bool = False
