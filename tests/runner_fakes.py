from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, create_autospec

from scraper.html_downloaders import (
    FallbackHtmlDownloader,
    HtmlDownloadAttempt,
    HtmlDownloadResult,
)
from scraper.sites import Scraper


class FakeScraper(Scraper):
    def __init__(
        self,
        *,
        name: str,
        url: str,
        limit: int,
        jobs: list[Any],
        requires_search_html: bool = True,
    ) -> None:
        super().__init__(url=url, limit=limit)
        self.name = name
        self.requires_search_html = requires_search_html
        self.parsed_html_pages: list[str] = []
        self._jobs = jobs

    def parse(self, html: str) -> list[Any]:
        self.parsed_html_pages.append(html)
        return self._jobs


def build_html_downloader_returning(
    html: str | None, attempts: tuple[HtmlDownloadAttempt, ...] = ()
) -> MagicMock:
    html_downloader = create_autospec(FallbackHtmlDownloader, instance=True)
    html_downloader.download_html.return_value = HtmlDownloadResult(html=html, attempts=attempts)
    return html_downloader
