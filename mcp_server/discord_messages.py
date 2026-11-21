from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from mcp_server.discord_settings import StoredDiscordSettings

TEXT_LIMIT = 2000
FILE_BYTE_LIMIT = 10_000_000
EMPTY_VALUE_TEXT = "-"
JOB_SEPARATOR = "\n\n---\n\n"
HARD_LINE_BREAK = "  "
CODE_FENCE = "```"
JAKARTA_TIMEZONE = timezone(timedelta(hours=7), "Asia/Jakarta")
PLACEHOLDER_PATTERN = re.compile(r"\{([A-Za-z_]\w*)\}")

MessageKind = Literal["text", "file"]


class MessageInvalidError(ValueError):
    pass


@dataclass(frozen=True)
class MessageAttachment:
    file_name: str
    file_text: str


@dataclass(frozen=True)
class DigestCounts:
    keyword_count: int | None = None
    site_count: int | None = None
    error_count: int | None = None


@dataclass(frozen=True)
class OutgoingMessage:
    kind: MessageKind
    title: str | None
    content: str
    mention_user_id: str | None = None
    attachment: MessageAttachment | None = None
    job_count: int = 0


def build_messages(
    settings: StoredDiscordSettings,
    mention: bool,
    text: str | None,
    jobs: list[dict[str, Any]] | None,
    digest_counts: DigestCounts | None = None,
    digest_date: date | None = None,
) -> tuple[OutgoingMessage, ...]:
    if (text is None) == (jobs is None):
        raise MessageInvalidError("give exactly one of text or jobs")
    mention_user_id = _pick_mention_user_id(settings, mention)
    if jobs is None:
        return (_build_text_message(mention_user_id, text),)
    chosen_date = digest_date
    if chosen_date is None:
        chosen_date = read_jakarta_today()
    chosen_counts = digest_counts
    if chosen_counts is None:
        chosen_counts = DigestCounts()
    return (_build_jobs_file_message(settings, mention_user_id, jobs, chosen_counts, chosen_date),)


def fill_job_template(template: str, job: Mapping[str, Any]) -> str:
    def fill_placeholder(match: re.Match[str]) -> str:
        return _format_placeholder_value(job.get(match.group(1)))

    return PLACEHOLDER_PATTERN.sub(fill_placeholder, template)


def read_jakarta_today() -> date:
    return datetime.now(JAKARTA_TIMEZONE).date()


def build_jobs_file_name(digest_date: date) -> str:
    return f"jobs-{digest_date.isoformat()}.md"


def _format_placeholder_value(placeholder_value: Any) -> str:
    if placeholder_value is None:
        return EMPTY_VALUE_TEXT
    value_text = str(placeholder_value)
    if not value_text.strip():
        return EMPTY_VALUE_TEXT
    return value_text


def _pick_mention_user_id(settings: StoredDiscordSettings, mention: bool) -> str | None:
    if not mention:
        return None
    if not settings.mention_user_id:
        return None
    return settings.mention_user_id


def _build_mention_prefix(mention_user_id: str | None) -> str:
    if mention_user_id is None:
        return ""
    return f"<@{mention_user_id}>\n"


def _build_text_message(mention_user_id: str | None, text: Any) -> OutgoingMessage:
    if not isinstance(text, str) or not text.strip():
        raise MessageInvalidError("text must not be empty")
    content = _build_mention_prefix(mention_user_id) + text
    if len(content) > TEXT_LIMIT:
        raise MessageInvalidError(
            f"text is {len(content)} characters with the mention, the limit is {TEXT_LIMIT}"
        )
    return OutgoingMessage(
        kind="text", title=None, content=content, mention_user_id=mention_user_id
    )


def _build_jobs_file_message(
    settings: StoredDiscordSettings,
    mention_user_id: str | None,
    jobs: Any,
    digest_counts: DigestCounts,
    digest_date: date,
) -> OutgoingMessage:
    _validate_jobs(jobs)
    file_name = build_jobs_file_name(digest_date)
    attachment = MessageAttachment(
        file_name=file_name,
        file_text=_build_jobs_file_text(settings.message_template, jobs),
    )
    _validate_file_size(attachment)
    content = _build_mention_prefix(mention_user_id) + _build_digest_text(
        jobs, digest_counts, digest_date
    )
    return OutgoingMessage(
        kind="file",
        title=file_name,
        content=content,
        mention_user_id=mention_user_id,
        attachment=attachment,
        job_count=len(jobs),
    )


def _validate_jobs(jobs: Any) -> None:
    if not isinstance(jobs, list) or not jobs:
        raise MessageInvalidError("jobs must hold at least 1 job")
    for job in jobs:
        if not isinstance(job, dict):
            raise MessageInvalidError("every job must be a mapping")


def _validate_file_size(attachment: MessageAttachment) -> None:
    byte_count = len(attachment.file_text.encode("utf-8"))
    if byte_count > FILE_BYTE_LIMIT:
        raise MessageInvalidError(
            f"the jobs file is {byte_count} bytes, the Discord upload limit is {FILE_BYTE_LIMIT}"
        )


def _build_jobs_file_text(template: str, jobs: list[dict[str, Any]]) -> str:
    rendered_jobs = []
    for job in jobs:
        job_text = fill_job_template(template, job).strip("\n")
        rendered_jobs.append(_add_hard_line_breaks(job_text))
    return JOB_SEPARATOR.join(rendered_jobs) + "\n"


def _add_hard_line_breaks(job_text: str) -> str:
    lines = job_text.split("\n")
    is_inside_code_fence = False
    broken_lines = []
    for index, line in enumerate(lines):
        if line.lstrip().startswith(CODE_FENCE):
            is_inside_code_fence = not is_inside_code_fence
            broken_lines.append(line)
            continue
        if is_inside_code_fence or not _is_followed_by_text_line(lines, index):
            broken_lines.append(line)
            continue
        broken_lines.append(line.rstrip() + HARD_LINE_BREAK)
    return "\n".join(broken_lines)


def _is_followed_by_text_line(lines: list[str], index: int) -> bool:
    if lines[index].strip() == "":
        return False
    is_last_line = index == len(lines) - 1
    if is_last_line:
        return False
    next_line = lines[index + 1]
    return next_line.strip() != ""


def _build_digest_text(
    jobs: list[dict[str, Any]], digest_counts: DigestCounts, digest_date: date
) -> str:
    keyword_count = _pick_count(
        "keyword_count", digest_counts.keyword_count, _count_distinct(jobs, "matched_keyword")
    )
    site_count = _pick_count("site_count", digest_counts.site_count, _count_distinct(jobs, "site"))
    error_count = _pick_count("error_count", digest_counts.error_count, 0)
    heading = f"**Job digest — {_format_long_date(digest_date)}**"
    scraped_line = (
        f"*Scraped {_format_job_count(len(jobs))} across {keyword_count} keyword(s) "
        f"and {site_count} site(s). Errors: {error_count}.*"
    )
    return f"{heading}\n\n{scraped_line}"


def _pick_count(name: str, given_count: Any, fallback_count: int) -> int:
    if given_count is None:
        return fallback_count
    if isinstance(given_count, bool) or not isinstance(given_count, int) or given_count < 0:
        raise MessageInvalidError(f"{name} must be a whole number of 0 or more")
    return given_count


def _count_distinct(jobs: list[dict[str, Any]], field_name: str) -> int:
    distinct_values = set()
    for job in jobs:
        field_value = job.get(field_name)
        if field_value is None or not str(field_value).strip():
            continue
        distinct_values.add(str(field_value))
    return len(distinct_values)


def _format_long_date(digest_date: date) -> str:
    return f"{digest_date:%A}, {digest_date.day} {digest_date:%B} {digest_date.year}"


def _format_job_count(job_count: int) -> str:
    if job_count == 1:
        return "1 job"
    return f"{job_count} jobs"
