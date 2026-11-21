# tests/test_log.py
from __future__ import annotations

import importlib
import logging
import sys
from collections.abc import Iterator

import pytest

import scraper.log as scraper_log

LOGGER_NAME = "job-scraper"
UNPARSEABLE_PROXY_URL_TEXT = "<unparseable proxy url>"


@pytest.fixture(autouse=True)
def _scraper_logger_gets_its_handlers_back_after_each_test() -> Iterator[None]:
    logger = logging.getLogger(LOGGER_NAME)
    scraper_handlers_before_test = _list_handlers_not_attached_by_pytest(logger)
    were_handlers_attached_before_test = scraper_log._are_handlers_attached
    yield
    for handler in _list_handlers_not_attached_by_pytest(logger):
        logger.removeHandler(handler)
    for handler in scraper_handlers_before_test:
        logger.addHandler(handler)
    scraper_log._are_handlers_attached = were_handlers_attached_before_test


def _list_handlers_not_attached_by_pytest(logger: logging.Logger) -> list[logging.Handler]:
    handlers_pytest_attaches_to_every_logger = logging.getLogger().handlers
    handlers_not_attached_by_pytest: list[logging.Handler] = []
    for handler in logger.handlers:
        if handler in handlers_pytest_attaches_to_every_logger:
            continue
        handlers_not_attached_by_pytest.append(handler)
    return handlers_not_attached_by_pytest


def _reload_log_module_and_get_logger() -> logging.Logger:
    importlib.reload(scraper_log)
    return scraper_log.get_scraper_logger()


def test_get_scraper_logger_returns_named_logger():
    logger = _reload_log_module_and_get_logger()

    assert logger.name == LOGGER_NAME


def test_get_scraper_logger_attaches_exactly_one_handler():
    logger = _reload_log_module_and_get_logger()

    assert len(_list_handlers_not_attached_by_pytest(logger)) == 1


def test_the_only_handler_is_a_debug_level_stream_handler_on_stdout():
    logger = _reload_log_module_and_get_logger()

    (handler,) = _list_handlers_not_attached_by_pytest(logger)

    assert type(handler) is logging.StreamHandler
    assert handler.stream is sys.stdout
    assert handler.level == logging.DEBUG


def test_logged_line_reaches_stdout_and_not_stderr(capsys: pytest.CaptureFixture[str]):
    logger = _reload_log_module_and_get_logger()

    logger.info("scrape started for %s", "glints")

    captured = capsys.readouterr()
    assert "[INFO] job-scraper: scrape started for glints" in captured.out
    assert captured.err == ""


def test_debug_line_reaches_stdout(capsys: pytest.CaptureFixture[str]):
    logger = _reload_log_module_and_get_logger()

    logger.debug("downloader detail")

    assert "[DEBUG] job-scraper: downloader detail" in capsys.readouterr().out


def test_logger_does_not_propagate_to_the_root_logger():
    logger = _reload_log_module_and_get_logger()

    assert logger.propagate is False
    assert logger.level == logging.DEBUG


def test_logging_creates_no_file_or_directory_in_the_working_directory(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(tmp_path)
    logger = _reload_log_module_and_get_logger()

    logger.info("scrape started")

    assert list(tmp_path.iterdir()) == []


def test_second_call_attaches_no_more_handlers():
    logger = _reload_log_module_and_get_logger()
    handlers_after_first_call = _list_handlers_not_attached_by_pytest(logger)

    scraper_log.get_scraper_logger()

    assert _list_handlers_not_attached_by_pytest(logger) == handlers_after_first_call


def test_reloading_the_module_leaves_exactly_one_handler():
    _reload_log_module_and_get_logger()

    logger = _reload_log_module_and_get_logger()

    assert len(_list_handlers_not_attached_by_pytest(logger)) == 1


def test_hide_proxy_password_replaces_password_with_stars():
    url = "http://user:secret@proxy.example.com:8080/path"  # pragma: allowlist secret

    redacted = scraper_log.hide_proxy_password(url)

    assert "secret" not in redacted
    assert "user:***" in redacted
    assert "proxy.example.com:8080" in redacted


def test_hide_proxy_password_hides_a_password_that_has_no_username():
    proxy_url = "http://:pass@host:8080"

    hidden_proxy_url = scraper_log.hide_proxy_password(proxy_url)

    assert hidden_proxy_url == "http://***@host:8080"


def test_hide_proxy_password_keeps_a_url_without_credentials_unchanged():
    proxy_url = "socks5://proxy.example.com:1080"

    hidden_proxy_url = scraper_log.hide_proxy_password(proxy_url)

    assert hidden_proxy_url == proxy_url


def test_hide_proxy_password_reports_an_unparseable_port_without_echoing_the_url():
    proxy_url = "http://host:notaport"

    hidden_proxy_url = scraper_log.hide_proxy_password(proxy_url)

    assert hidden_proxy_url == UNPARSEABLE_PROXY_URL_TEXT


@pytest.mark.parametrize("proxy_url", ["not a url", ""])
def test_hide_proxy_password_keeps_text_without_hostname_or_credentials_unchanged(
    proxy_url: str,
):
    hidden_proxy_url = scraper_log.hide_proxy_password(proxy_url)

    assert hidden_proxy_url == proxy_url


def test_hide_proxy_password_never_echoes_a_scheme_less_url_that_carries_credentials():
    proxy_url = "user:pass@host:1080"

    hidden_proxy_url = scraper_log.hide_proxy_password(proxy_url)

    assert hidden_proxy_url == UNPARSEABLE_PROXY_URL_TEXT
    assert "pass" not in hidden_proxy_url
