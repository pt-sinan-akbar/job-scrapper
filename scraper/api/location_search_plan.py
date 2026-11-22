from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType

import yaml

from ..log import get_scraper_logger

LOCATION_MAPPING_PATH = Path(__file__).with_name("location_mapping.yaml")

_CITY_LOCATIONS_KEY = "city_locations"
_COUNTRY_LOCATION_KEY = "country_location"
_SITES_KEY = "sites"


class LocationMappingError(ValueError):
    pass


@dataclass(frozen=True)
class LocationSearchPlan:
    city_values: tuple[str, ...]
    is_country_wide: bool

    def has_any_request(self) -> bool:
        if self.city_values:
            return True
        return self.is_country_wide


@dataclass(frozen=True)
class LocationMapping:
    city_locations: tuple[str, ...]
    country_location: str
    city_values_by_site: Mapping[str, Mapping[str, str]]


def build_location_search_plan(
    site_name: str, filter_locations: Iterable[str]
) -> LocationSearchPlan:
    location_mapping = read_location_mapping()
    city_value_by_lowercase_city = location_mapping.city_values_by_site.get(site_name)
    if city_value_by_lowercase_city is None:
        return _build_country_wide_only_plan()
    lowercase_filter_locations = _lowercase_and_drop_blank_locations(filter_locations)
    if not lowercase_filter_locations:
        return _build_country_wide_only_plan()
    lowercase_country_location = location_mapping.country_location.lower()
    picked_lowercase_cities: list[str] = []
    for lowercase_filter_location in lowercase_filter_locations:
        if lowercase_filter_location != lowercase_country_location:
            picked_lowercase_cities.append(lowercase_filter_location)
    return LocationSearchPlan(
        city_values=_collect_unique_city_values(
            site_name, picked_lowercase_cities, city_value_by_lowercase_city
        ),
        is_country_wide=lowercase_country_location in lowercase_filter_locations,
    )


def list_filter_location_options() -> list[str]:
    location_mapping = read_location_mapping()
    return [*location_mapping.city_locations, location_mapping.country_location]


def find_filter_location_option(location: str) -> str | None:
    lowercase_location = location.strip().lower()
    for location_option in list_filter_location_options():
        if location_option.lower() == lowercase_location:
            return location_option
    return None


def build_unknown_location_message(location: str) -> str:
    allowed_locations = ", ".join(list_filter_location_options())
    return f"unknown location: {location}. allowed: {allowed_locations}"


def is_country_location_picked(filter_locations: Iterable[str]) -> bool:
    lowercase_country_location = read_location_mapping().country_location.lower()
    return lowercase_country_location in _lowercase_and_drop_blank_locations(filter_locations)


@lru_cache(maxsize=1)
def read_location_mapping() -> LocationMapping:
    with LOCATION_MAPPING_PATH.open(encoding="utf-8") as location_mapping_file:
        yaml_content = yaml.safe_load(location_mapping_file)
    return _parse_location_mapping(yaml_content)


def _build_country_wide_only_plan() -> LocationSearchPlan:
    return LocationSearchPlan(city_values=(), is_country_wide=True)


def _lowercase_and_drop_blank_locations(filter_locations: Iterable[str]) -> list[str]:
    lowercase_filter_locations: list[str] = []
    for filter_location in filter_locations:
        lowercase_filter_location = filter_location.strip().lower()
        if lowercase_filter_location:
            lowercase_filter_locations.append(lowercase_filter_location)
    return lowercase_filter_locations


def _collect_unique_city_values(
    site_name: str,
    picked_lowercase_cities: list[str],
    city_value_by_lowercase_city: Mapping[str, str],
) -> tuple[str, ...]:
    unique_city_values: list[str] = []
    for picked_lowercase_city in picked_lowercase_cities:
        city_value = city_value_by_lowercase_city.get(picked_lowercase_city)
        if city_value is None:
            get_scraper_logger().warning(
                "[location-plan] %s has no search value for location '%s'; skipped",
                site_name,
                picked_lowercase_city,
            )
            continue
        if city_value not in unique_city_values:
            unique_city_values.append(city_value)
    return tuple(unique_city_values)


def _parse_location_mapping(yaml_content: object) -> LocationMapping:
    if not isinstance(yaml_content, dict):
        raise LocationMappingError(f"{LOCATION_MAPPING_PATH.name} must be a mapping")
    city_locations = yaml_content.get(_CITY_LOCATIONS_KEY)
    country_location = yaml_content.get(_COUNTRY_LOCATION_KEY)
    city_values_by_site = yaml_content.get(_SITES_KEY)
    if not isinstance(city_locations, list) or not city_locations:
        raise LocationMappingError(f"{_CITY_LOCATIONS_KEY} must be a non-empty list")
    if not isinstance(country_location, str) or not country_location.strip():
        raise LocationMappingError(f"{_COUNTRY_LOCATION_KEY} must be a non-empty text")
    if not isinstance(city_values_by_site, dict):
        raise LocationMappingError(f"{_SITES_KEY} must be a mapping")
    city_location_labels: list[str] = []
    for city_location in city_locations:
        city_location_labels.append(str(city_location))
    return LocationMapping(
        city_locations=tuple(city_location_labels),
        country_location=country_location.strip(),
        city_values_by_site=_lowercase_city_labels_of_every_site(city_values_by_site),
    )


def _lowercase_city_labels_of_every_site(
    city_values_by_site: dict[object, object],
) -> Mapping[str, Mapping[str, str]]:
    lowercase_city_values_by_site: dict[str, Mapping[str, str]] = {}
    for site_name, city_value_by_city in city_values_by_site.items():
        if not isinstance(city_value_by_city, dict):
            raise LocationMappingError(f"{_SITES_KEY}.{site_name} must be a mapping")
        city_value_by_lowercase_city: dict[str, str] = {}
        for city_location, city_value in city_value_by_city.items():
            city_value_by_lowercase_city[str(city_location).lower()] = str(city_value)
        lowercase_city_values_by_site[str(site_name)] = MappingProxyType(
            city_value_by_lowercase_city
        )
    return MappingProxyType(lowercase_city_values_by_site)
