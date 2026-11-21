from __future__ import annotations

import logging

import pytest

_LOG_LINE_FORMATTER = logging.Formatter("%(message)s")


def list_warning_or_above_log_lines(log_capture: pytest.LogCaptureFixture) -> list[str]:
    warning_or_above_log_lines: list[str] = []
    for log_record in log_capture.records:
        if log_record.levelno < logging.WARNING:
            continue
        warning_or_above_log_lines.append(_LOG_LINE_FORMATTER.format(log_record))
    return warning_or_above_log_lines


def list_log_lines_containing(log_lines: list[str], searched_text: str) -> list[str]:
    log_lines_containing_text: list[str] = []
    for log_line in log_lines:
        if searched_text in log_line:
            log_lines_containing_text.append(log_line)
    return log_lines_containing_text
