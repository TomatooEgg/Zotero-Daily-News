from md_render import markdown_to_html


def test_markdown_to_html_sanitizes_llm_html():
    html = markdown_to_html(
        '[bad](javascript:alert(1))\n\n'
        '<script>alert(1)</script>\n'
        '<img src="https://example.com/x.png" onerror="alert(1)">\n'
        '<a href="zotero://select/library/items/ABC123" onclick="alert(1)">Zotero</a>\n\n'
        '```mermaid\n'
        'graph TD\n'
        '```\n'
    )

    assert "<script" not in html
    assert "<img" not in html
    assert "javascript:" not in html
    assert "onclick" not in html
    assert 'href="zotero://select/library/items/ABC123"' in html
    assert 'class="language-mermaid"' in html
