from __future__ import annotations

from ..config import ACCEPT_LANGUAGE, USER_AGENT
from ..log import get_scraper_logger, hide_proxy_password
from .base import HtmlDownloadAttempt, detect_challenge

CHROME_IMPERSONATE = "chrome131"
_LOG = get_scraper_logger()


class CurlCffiHtmlDownloader:
    name = "curl_cffi"

    def __init__(self, proxy: str | None = None) -> None:
        self._proxy = proxy

    def download_html(self, url: str) -> tuple[str | None, HtmlDownloadAttempt]:
        try:
            from curl_cffi import requests as cffi_requests  # type: ignore[attr-defined]
        except Exception as exc:
            _LOG.warning("[curl_cffi] not installed: %s", exc)
            return None, HtmlDownloadAttempt(
                downloader=self.name,
                code="not_installed",
                detail=f"{type(exc).__name__}: {exc}",
            )

        if self._proxy:
            _LOG.info("[curl_cffi] using proxy: %s", hide_proxy_password(self._proxy))

        try:
            proxies = {"http": self._proxy, "https": self._proxy} if self._proxy else None
            response = cffi_requests.get(
                url,
                impersonate=CHROME_IMPERSONATE,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept-Language": ACCEPT_LANGUAGE,
                },
                timeout=30,
                proxies=proxies,
            )
        except Exception as exc:
            _LOG.error("[curl_cffi] error on %s: %s", url, exc)
            return None, HtmlDownloadAttempt(
                downloader=self.name,
                code="runtime_error",
                detail=f"{type(exc).__name__}: {exc}",
            )

        status = response.status_code
        if status != 200:
            _LOG.warning("[curl_cffi] %s status=%d", url, status)
            return None, HtmlDownloadAttempt(
                downloader=self.name,
                code=f"http_{status}",
                detail=f"status={status}",
            )

        text = response.text
        challenge = detect_challenge(text)
        if challenge:
            _LOG.warning("[curl_cffi] %s blocked by challenge page", url)
            return None, HtmlDownloadAttempt(
                downloader=self.name,
                code="challenge",
                detail=challenge,
            )
        return text, HtmlDownloadAttempt(downloader=self.name, code="ok")
