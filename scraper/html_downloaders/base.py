from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ..config import CHALLENGE_MARKERS
from ..log import get_scraper_logger

_LOG = get_scraper_logger()

_TITLE_RE = re.compile(r"<title[^>]*>([^<]+)</title>", re.IGNORECASE)
_CHALLENGE_TITLES = (
    "just a moment",
    "attention required",
    "access denied",
    "security check",
    "verify you are human",
    "checking your browser",
)


def detect_challenge(html: str) -> str | None:
    match = _TITLE_RE.search(html)
    if match:
        title = match.group(1).strip()
        lowered = title.lower()
        for marker in _CHALLENGE_TITLES:
            if marker in lowered:
                return f"title={title}"
    if len(html) < 4096:
        for marker in CHALLENGE_MARKERS:
            if marker in html:
                return f"marker={marker}"
    return None


def looks_like_challenge(html: str) -> bool:
    return detect_challenge(html) is not None


@dataclass(frozen=True)
class HtmlDownloadAttempt:
    downloader: str
    code: str
    detail: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {"downloader": self.downloader, "code": self.code, "detail": self.detail}


@dataclass(frozen=True)
class HtmlDownloadResult:
    html: str | None
    attempts: tuple[HtmlDownloadAttempt, ...]


@runtime_checkable
class HtmlDownloader(Protocol):
    name: str

    def download_html(self, url: str) -> tuple[str | None, HtmlDownloadAttempt]: ...


class FallbackHtmlDownloader:
    def __init__(self, html_downloaders: list[HtmlDownloader]) -> None:
        self._html_downloaders = html_downloaders

    def download_html(self, url: str) -> HtmlDownloadResult:
        attempts: list[HtmlDownloadAttempt] = []
        for html_downloader in self._html_downloaders:
            _LOG.debug("[html_downloader] trying %s for %s", html_downloader.name, url)
            html, attempt = html_downloader.download_html(url)
            attempts.append(attempt)
            if html and attempt.code == "ok":
                return HtmlDownloadResult(html=html, attempts=tuple(attempts))
            _LOG.debug(
                "[html_downloader] %s insufficient (%s), falling through",
                html_downloader.name,
                attempt.code,
            )
        return HtmlDownloadResult(html=None, attempts=tuple(attempts))
