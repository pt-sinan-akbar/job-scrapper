from __future__ import annotations

from abc import ABC, abstractmethod

from ..types import Job


class Scraper(ABC):
    name: str
    requires_search_html: bool = True
    # True: the runner never fetches or parses HTML for this site
    api_only: bool = False

    def __init__(self, url: str, limit: int) -> None:
        self.url = url
        self.limit = limit

    @abstractmethod
    def parse(self, html: str) -> list[Job]: ...

    def parse_detail(self, html: str) -> str | None:
        return None
