from __future__ import annotations

from scraper.sites._markdown import html_to_markdown


def test_inline_tags_stay_on_same_line():
    html = "<p>Develop visuals using <b>Generative AI</b> for campaigns.</p>"
    assert html_to_markdown(html) == "Develop visuals using **Generative AI** for campaigns."


def test_lists_use_dash_bullets():
    html = "<ul><li>Python</li><li>SQL</li></ul>"
    assert html_to_markdown(html) == "- Python\n- SQL"


def test_headings_use_atx_style():
    html = "<h2>Requirements</h2><p>Golang</p>"
    assert html_to_markdown(html) == "## Requirements\n\nGolang"


def test_br_becomes_line_break():
    assert html_to_markdown("Line one<br>Line two") == "Line one\nLine two"


def test_drops_images_scripts_and_styles():
    html = "<p>Hi</p><img src='x.png'><script>alert(1)</script><style>p{}</style>"
    assert html_to_markdown(html) == "Hi"


def test_collapses_blank_lines():
    html = "<p>One</p><p></p><p></p><p>Two</p>"
    assert html_to_markdown(html) == "One\n\nTwo"


def test_plain_text_passes_through():
    text = "Pengalaman menjadi Devops\nFull wfo di jakarta"
    assert html_to_markdown(text) == text


def test_empty_input_returns_none():
    assert html_to_markdown(None) is None
    assert html_to_markdown("   ") is None
    assert html_to_markdown("<p> </p>") is None


def test_plain_text_keeps_paragraph_breaks():
    text = "Intro\n\nSecond para\n\n\n\nThird"
    assert html_to_markdown(text) == "Intro\n\nSecond para\n\nThird"


def test_plain_text_keeps_angle_bracket_text():
    text = "Email <hr@co.com> with <Your CV> and <name>"
    assert html_to_markdown(text) == text


def test_plain_text_normalises_line_endings_and_trailing_spaces():
    assert html_to_markdown("One  \r\nTwo\r\n") == "One\nTwo"


def test_plain_text_underline_does_not_become_heading():
    assert html_to_markdown("Skills\n---\nPython\n===") == "Skills\n\\---\nPython\n\\==="


def test_plain_text_keeps_divider_after_blank_line():
    assert html_to_markdown("Intro\n\n---\n\nMore") == "Intro\n\n---\n\nMore"


def test_html_escapes_line_leading_markdown():
    assert html_to_markdown("<p># Hash</p>") == "\\# Hash"
    assert html_to_markdown("<p>1. Not a list</p>") == "1\\. Not a list"
    assert html_to_markdown("<p>> Not a quote</p>") == "\\> Not a quote"
    assert html_to_markdown("<p>+ Not a bullet</p>") == "\\+ Not a bullet"


def test_html_escapes_asterisks_inside_bold():
    assert html_to_markdown("<b>5*</b> hotel") == "**5\\*** hotel"


def test_html_escapes_only_word_edge_underscores():
    assert html_to_markdown("<p>snake_case and _x_</p>") == "snake_case and \\_x\\_"


def test_html_keeps_inline_hyphens_readable():
    assert html_to_markdown("<p>Jakarta-Bandung, full-time</p>") == "Jakarta-Bandung, full-time"


def test_break_at_end_of_bold_text_keeps_heading_apart_from_next_text():
    html = (
        "<div><strong>About Us<br><br></strong><strong>GoTyme</strong> is a bank."
        "<br><br><strong>About The Role<br><br></strong>We are hiring</div>"
    )
    assert html_to_markdown(html) == (
        "**About Us**\n\n**GoTyme** is a bank.\n\n**About The Role**\n\nWe are hiring"
    )


def test_break_at_start_of_bold_text_stays_before_the_bold_text():
    html = "<div>Intro<strong><br>Requirements</strong> below</div>"
    assert html_to_markdown(html) == "Intro\n**Requirements** below"


def test_break_at_end_of_nested_inline_tags_moves_out_of_every_tag():
    html = "<div><strong><u>Your role<br><br></u></strong>Build models</div>"
    assert html_to_markdown(html) == "**Your role**\n\nBuild models"


def test_break_in_the_middle_of_bold_text_stays_inside():
    html = "<div><strong>Line one<br>Line two</strong></div>"
    assert html_to_markdown(html) == "**Line one\nLine two**"


def test_bold_text_nested_in_bold_text_is_marked_bold_once():
    html = "<div><strong><strong>Who are we looking for</strong><br></strong>Engineers</div>"
    assert html_to_markdown(html) == "**Who are we looking for**\nEngineers"


def test_break_before_trailing_whitespace_in_bold_text_still_moves_out():
    assert html_to_markdown("<p><strong>Title<br>\n</strong>Text</p>") == "**Title**\nText"
    assert html_to_markdown("<p><strong>Title<br> </strong>Text</p>") == "**Title**\nText"


def test_break_after_leading_whitespace_in_bold_text_still_moves_out():
    assert (
        html_to_markdown("<p>Intro<strong> <br>Title</strong> text</p>") == "Intro\n **Title** text"
    )
