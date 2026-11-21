from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest

from mcp_server import discord_messages
from mcp_server.discord_messages import (
    FILE_BYTE_LIMIT,
    TEXT_LIMIT,
    DigestCounts,
    MessageInvalidError,
    build_jobs_file_name,
    build_messages,
    fill_job_template,
    read_jakarta_today,
)
from mcp_server.discord_settings import StoredDiscordSettings

USER_ID = "98765432109876543"
TEMPLATE = "## {title}\n{company} | {location}\n{url}"
DIGEST_DATE = date(2026, 11, 21)


def make_settings(**overrides: Any) -> StoredDiscordSettings:
    fields: dict[str, Any] = {
        "token": None,
        "default_channel_id": None,
        "mention_user_id": USER_ID,
        "message_template": TEMPLATE,
        "max_chars": 1900,
        "updated_at": None,
    }
    return StoredDiscordSettings(**{**fields, **overrides})


def make_job(index: int = 1, **overrides: Any) -> dict[str, Any]:
    return {
        "title": f"Job {index}",
        "company": "Acme",
        "location": "Jakarta",
        "url": f"https://example.com/{index}",
        **overrides,
    }


def test_fill_job_template_fills_placeholders():
    assert fill_job_template(TEMPLATE, make_job()) == (
        "## Job 1\nAcme | Jakarta\nhttps://example.com/1"
    )


def test_fill_job_template_turns_missing_null_and_blank_fields_into_a_dash():
    job = {"title": "Only title", "company": None, "location": "  "}

    assert fill_job_template(TEMPLATE, job) == "## Only title\n- | -\n-"


def test_fill_job_template_keeps_zero_as_a_value():
    assert fill_job_template("{salary_min}", {"salary_min": 0}) == "0"


def test_fill_job_template_leaves_unknown_braces_alone():
    assert fill_job_template("{title} {x y} {0} } { {", {"title": "T"}) == "T {x y} {0} } { {"


def test_fill_job_template_stringifies_numbers():
    assert fill_job_template("{salary_min}", {"salary_min": 5000}) == "5000"


def test_fill_job_template_does_not_expand_placeholders_inside_values():
    assert fill_job_template("{title}", {"title": "{company}", "company": "Acme"}) == "{company}"


def test_build_text_message():
    messages = build_messages(make_settings(), mention=False, text="hello **world**", jobs=None)

    assert [(m.kind, m.title, m.content) for m in messages] == [("text", None, "hello **world**")]


def test_build_text_message_with_mention_prefix():
    messages = build_messages(make_settings(), mention=True, text="hi", jobs=None)

    assert messages[0].content == f"<@{USER_ID}>\nhi"


def test_mention_is_ignored_when_no_user_is_saved():
    settings = make_settings(mention_user_id=None)

    messages = build_messages(settings, mention=True, text="hi", jobs=None)

    assert messages[0].content == "hi"


def test_text_limit_counts_the_mention_prefix():
    prefix_length = len(f"<@{USER_ID}>\n")

    build_messages(
        make_settings(), mention=True, text="a" * (TEXT_LIMIT - prefix_length), jobs=None
    )
    with pytest.raises(MessageInvalidError, match="2000"):
        build_messages(
            make_settings(), mention=True, text="a" * (TEXT_LIMIT - prefix_length + 1), jobs=None
        )


def test_text_of_exactly_the_limit_is_fine_without_mention():
    build_messages(make_settings(), mention=False, text="a" * TEXT_LIMIT, jobs=None)
    with pytest.raises(MessageInvalidError):
        build_messages(make_settings(), mention=False, text="a" * (TEXT_LIMIT + 1), jobs=None)


@pytest.mark.parametrize("text", ["", "   \n"])
def test_empty_text_is_invalid(text: str):
    with pytest.raises(MessageInvalidError, match="text"):
        build_messages(make_settings(), mention=False, text=text, jobs=None)


def test_text_that_is_not_a_string_is_invalid():
    with pytest.raises(MessageInvalidError):
        build_messages(make_settings(), mention=False, text=5, jobs=None)  # type: ignore[arg-type]


def test_both_text_and_jobs_is_invalid():
    with pytest.raises(MessageInvalidError, match="exactly one"):
        build_messages(make_settings(), mention=False, text="hi", jobs=[make_job()])


def test_neither_text_nor_jobs_is_invalid():
    with pytest.raises(MessageInvalidError, match="exactly one"):
        build_messages(make_settings(), mention=False, text=None, jobs=None)


def build_jobs_message(
    jobs: list[dict[str, Any]],
    mention: bool = False,
    settings: StoredDiscordSettings | None = None,
    digest_counts: DigestCounts | None = None,
) -> discord_messages.OutgoingMessage:
    [message] = build_messages(
        settings or make_settings(),
        mention=mention,
        text=None,
        jobs=jobs,
        digest_counts=digest_counts,
        digest_date=DIGEST_DATE,
    )
    return message


def test_empty_jobs_list_is_invalid():
    with pytest.raises(MessageInvalidError, match="at least 1 job"):
        build_messages(make_settings(), mention=False, text=None, jobs=[])


def test_jobs_that_are_not_mappings_are_invalid():
    with pytest.raises(MessageInvalidError, match="job"):
        build_messages(make_settings(), mention=False, text=None, jobs=["nope"])  # type: ignore[list-item]


def test_jobs_become_one_file_message():
    message = build_jobs_message([make_job(1), make_job(2)])

    assert message.kind == "file"
    assert message.title == "jobs-2026-11-21.md"
    assert message.job_count == 2
    assert message.attachment is not None
    assert message.attachment.file_name == "jobs-2026-11-21.md"


def test_jobs_file_holds_every_job_split_by_a_rule_line():
    message = build_jobs_message([make_job(1), make_job(2)])

    assert message.attachment is not None
    assert message.attachment.file_text == (
        "## Job 1  \nAcme | Jakarta  \nhttps://example.com/1"
        "\n\n---\n\n"
        "## Job 2  \nAcme | Jakarta  \nhttps://example.com/2\n"
    )


def test_jobs_file_keeps_each_template_line_on_its_own_row():
    settings = make_settings(message_template="**Details**\nLink: {url}\nSource: {site}\n\nNext")

    message = build_jobs_message([{"url": "u", "site": "jobstreet"}], settings=settings)

    assert message.attachment is not None
    assert message.attachment.file_text == ("**Details**  \nLink: u  \nSource: jobstreet\n\nNext\n")


def test_jobs_file_leaves_code_blocks_alone():
    settings = make_settings(message_template="Intro\n```\na\nb\n```\nOutro")

    message = build_jobs_message([{}], settings=settings)

    assert message.attachment is not None
    assert message.attachment.file_text == "Intro  \n```\na\nb\n```\nOutro\n"


def test_jobs_file_trims_blank_lines_around_each_job():
    settings = make_settings(message_template="\n{title}\n\n")

    message = build_jobs_message([make_job(1), make_job(2)], settings=settings)

    assert message.attachment is not None
    assert message.attachment.file_text == "Job 1\n\n---\n\nJob 2\n"


def test_jobs_file_fills_empty_values_with_a_dash():
    message = build_jobs_message([{"title": "Only title", "company": None}])

    assert message.attachment is not None
    assert message.attachment.file_text == "## Only title  \n- | -  \n-\n"


def test_jobs_file_never_cuts_a_long_job_and_ignores_max_chars():
    settings = make_settings(max_chars=10, message_template="{title}")

    message = build_jobs_message([make_job(title="x" * 5000)], settings=settings)

    assert message.attachment is not None
    assert message.attachment.file_text == "x" * 5000 + "\n"


def test_more_than_fifty_jobs_still_make_one_message():
    jobs = [make_job(index) for index in range(120)]

    message = build_jobs_message(jobs)

    assert message.job_count == 120
    assert message.attachment is not None
    assert message.attachment.file_text.count("\n---\n") == 119


def test_jobs_file_over_the_upload_limit_is_invalid():
    settings = make_settings(message_template="{title}")
    jobs = [make_job(title="x" * (FILE_BYTE_LIMIT // 2)), make_job(title="y" * 10)]
    jobs.append(make_job(title="z" * (FILE_BYTE_LIMIT // 2)))

    with pytest.raises(MessageInvalidError, match="10000000"):
        build_jobs_message(jobs, settings=settings)


def test_jobs_file_size_counts_bytes_not_characters():
    settings = make_settings(message_template="{title}")
    job = make_job(title="é" * (FILE_BYTE_LIMIT // 2 + 1))

    with pytest.raises(MessageInvalidError, match="upload limit"):
        build_jobs_message([job], settings=settings)


def test_digest_text_uses_the_given_counts():
    counts = DigestCounts(keyword_count=11, site_count=4, error_count=2)

    message = build_jobs_message([make_job(1), make_job(2)], digest_counts=counts)

    assert message.content == (
        "**Job digest — Saturday, 21 November 2026**\n"
        "\n"
        "*Scraped 2 jobs across 11 keyword(s) and 4 site(s). Errors: 2.*"
    )


def test_digest_counts_default_to_distinct_keywords_and_sites_and_no_errors():
    jobs = [
        make_job(1, matched_keyword="django", site="upwork"),
        make_job(2, matched_keyword="django", site="glints"),
        make_job(3, matched_keyword="flask", site="glints"),
        make_job(4, matched_keyword=None, site=" "),
    ]

    message = build_jobs_message(jobs)

    assert message.content.endswith(
        "*Scraped 4 jobs across 2 keyword(s) and 2 site(s). Errors: 0.*"
    )


def test_digest_text_says_one_job_for_a_single_job():
    message = build_jobs_message([make_job(1, matched_keyword="go", site="upwork")])

    assert "*Scraped 1 job across 1 keyword(s) and 1 site(s). Errors: 0.*" in message.content


@pytest.mark.parametrize("bad_count", [-1, 1.5, "3", True])
def test_digest_count_that_is_not_a_whole_number_is_invalid(bad_count: Any):
    counts = DigestCounts(keyword_count=bad_count)

    with pytest.raises(MessageInvalidError, match="keyword_count"):
        build_jobs_message([make_job(1)], digest_counts=counts)


def test_digest_message_starts_with_the_mention_when_mention_is_on():
    message = build_jobs_message([make_job(1)], mention=True)

    assert message.content.startswith(f"<@{USER_ID}>\n**Job digest — Saturday")
    assert message.mention_user_id == USER_ID


def test_digest_message_has_no_mention_when_mention_is_off():
    message = build_jobs_message([make_job(1)], mention=False)

    assert message.content.startswith("**Job digest")
    assert message.mention_user_id is None


def test_digest_message_has_no_mention_when_no_user_is_saved():
    settings = make_settings(mention_user_id=None)

    message = build_jobs_message([make_job(1)], mention=True, settings=settings)

    assert message.content.startswith("**Job digest")
    assert message.mention_user_id is None


def test_a_job_title_with_a_mention_never_sets_the_mention_user_id():
    job = make_job(1, title="<@123456789012345678>")

    message = build_jobs_message([job], mention=False)

    assert message.mention_user_id is None


def test_text_message_carries_the_mention_user_id():
    messages = build_messages(make_settings(), mention=True, text="hi", jobs=None)

    assert messages[0].mention_user_id == USER_ID
    assert messages[0].attachment is None
    assert messages[0].job_count == 0


def test_jobs_file_name_uses_the_iso_date():
    assert build_jobs_file_name(date(2026, 1, 5)) == "jobs-2026-01-05.md"


def test_jobs_message_uses_today_in_jakarta_when_no_date_is_given(monkeypatch):
    monkeypatch.setattr(discord_messages, "read_jakarta_today", lambda: date(2026, 12, 31))

    [message] = build_messages(make_settings(), mention=False, text=None, jobs=[make_job(1)])

    assert message.title == "jobs-2026-12-31.md"
    assert "Thursday, 31 December 2026" in message.content


def test_jakarta_today_rolls_over_seven_hours_before_utc(monkeypatch):
    class LateUtcDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 20, 18, 30, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr(discord_messages, "datetime", LateUtcDatetime)

    assert read_jakarta_today() == date(2026, 11, 21)
