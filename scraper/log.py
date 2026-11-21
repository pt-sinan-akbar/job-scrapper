from __future__ import annotations

import logging
import sys
from urllib.parse import ParseResult, urlparse, urlunparse

_LOGGER_NAME = "job-scraper"
_LOG_LINE_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_HIDDEN_PASSWORD_TEXT = "***"
_UNPARSEABLE_PROXY_URL_TEXT = "<unparseable proxy url>"

_are_handlers_attached: bool = False


def get_scraper_logger() -> logging.Logger:
    global _are_handlers_attached

    logger = logging.getLogger(_LOGGER_NAME)
    if _are_handlers_attached:
        return logger

    _attach_stdout_handler(logger)
    _are_handlers_attached = True
    return logger


def hide_proxy_password(proxy_url: str) -> str:
    try:
        parsed_proxy_url = urlparse(proxy_url)
        hostname = parsed_proxy_url.hostname
        if not hostname:
            return _hide_proxy_url_that_has_no_hostname(proxy_url)
        host_with_hidden_password = _build_host_with_hidden_password(parsed_proxy_url, hostname)
        return urlunparse(
            (
                parsed_proxy_url.scheme,
                host_with_hidden_password,
                parsed_proxy_url.path,
                parsed_proxy_url.params,
                parsed_proxy_url.query,
                parsed_proxy_url.fragment,
            )
        )
    except Exception:
        return _UNPARSEABLE_PROXY_URL_TEXT


def _attach_stdout_handler(logger: logging.Logger) -> None:
    _remove_handlers_left_by_earlier_module_load(logger)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    log_line_formatter = logging.Formatter(_LOG_LINE_FORMAT)
    logger.addHandler(_build_stdout_handler(log_line_formatter))


def _remove_handlers_left_by_earlier_module_load(logger: logging.Logger) -> None:
    logger.handlers.clear()


def _build_stdout_handler(log_line_formatter: logging.Formatter) -> logging.StreamHandler:
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.DEBUG)
    stdout_handler.setFormatter(log_line_formatter)
    return stdout_handler


def _hide_proxy_url_that_has_no_hostname(proxy_url: str) -> str:
    if "@" in proxy_url:
        return _UNPARSEABLE_PROXY_URL_TEXT
    return proxy_url


def _build_host_with_hidden_password(parsed_proxy_url: ParseResult, hostname: str) -> str:
    host_with_port = _build_host_with_port(hostname, parsed_proxy_url.port)
    username = parsed_proxy_url.username
    if username is not None and username != "":
        return f"{username}:{_HIDDEN_PASSWORD_TEXT}@{host_with_port}"
    if parsed_proxy_url.password is not None:
        return f"{_HIDDEN_PASSWORD_TEXT}@{host_with_port}"
    return host_with_port


def _build_host_with_port(hostname: str, port: int | None) -> str:
    if not port:
        return hostname
    return f"{hostname}:{port}"
