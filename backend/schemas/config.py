from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

MAX_LIMIT = 200
MAX_AGE_HOURS = 720
MAX_LIST_ITEMS = 100
MAX_DELAY_SECONDS = 60

Keyword = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
SiteName = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_-]+$", max_length=40)]
FieldName = Annotated[str, StringConstraints(pattern=r"^[a-z_]+$", max_length=40)]
TextItem = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
TextList = Annotated[list[TextItem], Field(max_length=MAX_LIST_ITEMS)]
FieldList = Annotated[list[FieldName], Field(max_length=MAX_LIST_ITEMS)]
Delay = Annotated[float, Field(ge=0, le=MAX_DELAY_SECONDS)]


class FilterSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location: TextList = Field(default_factory=list, description="Keep only jobs in these places")
    employment_type: TextList = Field(
        default_factory=list, description="Keep only these types, like `full_time`"
    )
    work_type: TextList = Field(
        default_factory=list, description="Keep only these, like `remote` or `hybrid`"
    )


class ApiSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(description="Use the site API, `false` reads the web page only")
    delay_seconds: tuple[Delay, Delay] | None = Field(
        default=None, description="Random pause between API calls, `[min, max]` seconds"
    )
    locations: Any = Field(default=None, exclude=True)
    country_wide: Any = Field(default=None, exclude=True)


class SiteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = Field(default=None, description="Turn the site on or off")
    limit: int | None = Field(
        default=None,
        ge=1,
        le=MAX_LIMIT,
        description=f"Most jobs to keep per keyword, 1 to {MAX_LIMIT}",
    )
    max_age_hours: int | None = Field(
        default=None,
        ge=1,
        le=MAX_AGE_HOURS,
        description=f"Skip jobs older than this, up to {MAX_AGE_HOURS}",
    )
    filter: FilterSettings | None = Field(default=None, description="Keep only matching jobs")
    api: ApiSettings | None = Field(default=None, description="Site API settings")

    @field_validator("limit", "filter", mode="before")
    @classmethod
    def _refuse_null(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("cannot be null")
        return value


class ConfigUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1, description="`version` from `GET /api/config`")
    fields: FieldList | None = Field(
        default=None, description="Job fields to keep, names from `job_fields`"
    )
    sites: dict[SiteName, SiteUpdate] = Field(
        default_factory=dict, description="Settings per site, keyed by site name"
    )

    def to_patch(self) -> dict[str, Any]:
        # exclude_unset keeps explicit nulls, which remove a key from the settings
        return self.model_dump(mode="json", exclude_unset=True, exclude={"version"})
