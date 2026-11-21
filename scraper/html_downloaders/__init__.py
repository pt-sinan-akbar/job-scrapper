from __future__ import annotations

from .base import (
    FallbackHtmlDownloader,
    HtmlDownloadAttempt,
    HtmlDownloader,
    HtmlDownloadResult,
    detect_challenge,
    looks_like_challenge,
)
from .cloudscraper import CloudscraperHtmlDownloader
from .curl_cffi import CurlCffiHtmlDownloader
from .playwright import PlaywrightHtmlDownloader

__all__ = [
    "FallbackHtmlDownloader",
    "HtmlDownloadResult",
    "HtmlDownloadAttempt",
    "HtmlDownloader",
    "CloudscraperHtmlDownloader",
    "CurlCffiHtmlDownloader",
    "PlaywrightHtmlDownloader",
    "detect_challenge",
    "looks_like_challenge",
]
