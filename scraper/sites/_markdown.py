from __future__ import annotations

import re
from collections.abc import Iterable

from bs4 import BeautifulSoup, NavigableString, PageElement, Tag
from markdownify import ATX, MarkdownConverter

_DROPPED_TAGS = ("img", "script", "style", "noscript", "iframe", "svg")
_BOLD_TAGS = ("b", "strong")
_INLINE_TAGS = (*_BOLD_TAGS, "i", "em", "u", "a", "span", "font")
_LINE_BREAK_TAG = "br"
_HTML_TAG_RE = re.compile(
    r"</?(?:p|div|br|hr|ul|ol|li|h[1-6]|b|strong|i|em|u|a|span|font|small|sub|sup"
    r"|table|thead|tbody|tr|td|th|section|article|blockquote|pre|code)(?=[\s/>])[^>]*>",
    re.IGNORECASE,
)
_TRAILING_WS_RE = re.compile(r"[ \t]+\n")
_BLANK_LINES_RE = re.compile(r"\n{3,}")
_SETEXT_UNDERLINE_RE = re.compile(r"(?<=[^\n]\n)([-=]+)$", re.MULTILINE)
_LINE_MARKER_RE = re.compile(r"(\s|^)(#{1,6}|[-=+>]+)(?=\s|$)")
_ORDERED_MARKER_RE = re.compile(r"(\s|^)(\d{1,9})([.)])(?=\s|$)")
_EDGE_UNDERSCORE_RE = re.compile(r"(?<!\w)_|_(?!\w)")


class _JobMarkdownConverter(MarkdownConverter):
    def escape(self, text: str, parent_tags: set[str]) -> str:
        if not text:
            return ""
        text = text.replace("*", r"\*")
        text = _EDGE_UNDERSCORE_RE.sub(r"\\_", text)
        text = _LINE_MARKER_RE.sub(r"\1\\\2", text)
        return _ORDERED_MARKER_RE.sub(r"\1\2\\\3", text)


_CONVERTER = _JobMarkdownConverter(heading_style=ATX, bullets="-")


def _tidy(markdown: str) -> str | None:
    markdown = _TRAILING_WS_RE.sub("\n", markdown)
    markdown = _BLANK_LINES_RE.sub("\n\n", markdown).strip()
    return markdown or None


def _plain_text_to_markdown(text: str) -> str | None:
    text = text.replace("\r\n", "\n").replace("\r", "\n") + "\n"
    tidied = _tidy(text)
    return _SETEXT_UNDERLINE_RE.sub(r"\\\1", tidied) if tidied else None


def html_to_markdown(html: str | None) -> str | None:
    """Convert a job description HTML fragment to Markdown; plain text keeps its layout."""
    if not html or not html.strip():
        return None
    if not _HTML_TAG_RE.search(html):
        return _plain_text_to_markdown(html)
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(_DROPPED_TAGS):
        tag.decompose()
    _unwrap_bold_tags_nested_in_bold_tags(soup)
    _move_edge_line_breaks_out_of_inline_tags(soup)
    return _tidy(_CONVERTER.convert_soup(soup))


def _unwrap_bold_tags_nested_in_bold_tags(soup: BeautifulSoup) -> None:
    for bold_tag in soup.find_all(_BOLD_TAGS):
        if bold_tag.find_parent(_BOLD_TAGS) is not None:
            bold_tag.unwrap()


def _move_edge_line_breaks_out_of_inline_tags(soup: BeautifulSoup) -> None:
    inline_tags = soup.find_all(_INLINE_TAGS)
    for inline_tag in reversed(inline_tags):
        _move_trailing_line_breaks_after_tag(inline_tag)
        _move_leading_line_breaks_before_tag(inline_tag)


def _move_trailing_line_breaks_after_tag(inline_tag: Tag) -> None:
    while True:
        trailing_line_break = _find_first_line_break_past_blank_text(reversed(inline_tag.contents))
        if trailing_line_break is None:
            return
        inline_tag.insert_after(trailing_line_break.extract())


def _move_leading_line_breaks_before_tag(inline_tag: Tag) -> None:
    while True:
        leading_line_break = _find_first_line_break_past_blank_text(inline_tag.contents)
        if leading_line_break is None:
            return
        inline_tag.insert_before(leading_line_break.extract())


def _find_first_line_break_past_blank_text(
    children_from_edge: Iterable[PageElement],
) -> PageElement | None:
    for child in children_from_edge:
        if _is_blank_text(child):
            continue
        if _is_line_break(child):
            return child
        return None
    return None


def _is_blank_text(page_element: PageElement) -> bool:
    return isinstance(page_element, NavigableString) and not page_element.strip()


def _is_line_break(page_element: PageElement) -> bool:
    return isinstance(page_element, Tag) and page_element.name == _LINE_BREAK_TAG
