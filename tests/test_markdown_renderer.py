from app.ui.markdown_renderer import markdown_to_html


def test_table_renders_as_real_html_table():
    html = markdown_to_html(
        "| Specification | Value |\n"
        "|---|---|\n"
        "| CPU | Ryzen 5 5600X |\n"
        "| Cores | 6 |"
    )
    assert "<table>" in html
    assert "<th>Specification</th>" in html
    assert "<td>Ryzen 5 5600X</td>" in html
    assert "| - |" not in html


def test_common_rich_text_is_rendered():
    html = markdown_to_html(
        "### Heading\n\n**bold** and *italic* with `code`.\n\n"
        "- one\n- two\n\n> quote"
    )
    assert "<h3>Heading</h3>" in html
    assert "<strong>bold</strong>" in html
    assert "<em>italic</em>" in html
    assert "<code>code</code>" in html
    assert "<ul>" in html
    assert "<li>one</li>" in html
    assert "<blockquote>quote</blockquote>" in html


def test_fenced_code_is_escaped():
    html = markdown_to_html("```python\nprint('<hello>')\n```")
    assert "<pre><code" in html
    assert "print(&#x27;&lt;hello&gt;&#x27;)" in html


def test_escaped_heading_marker_is_normalized():
    html = markdown_to_html(r"\### CPU instruction cycle")
    assert "<p>### CPU instruction cycle</p>" in html
    assert "\\###" not in html
