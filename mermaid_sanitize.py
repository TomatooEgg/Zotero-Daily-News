"""深度解读 Markdown 写入/渲染前的 Mermaid 与下标轻量清洗。"""

from __future__ import annotations

import re

_FENCE_RE = re.compile(r"(```[\s\S]*?```)")
_INLINE_MATH_RE = re.compile(r"\$[^$\n]+\$")
_BARE_UNDERSCORE_RE = re.compile(
    r"(?<![\\$`])([\u0370-\u03FF\u1D00-\u1DBF\w\u0300-\u036F])_(\{|[A-Za-z0-9])"
)
_MERMAID_FENCE_RE = re.compile(r"```mermaid[\s\S]*?```", re.I)
_TABLE_ROW_RE = re.compile(r"^\s*\|")
_UNESCAPED_PIPE_RE = re.compile(r"(?<!\\)\|")


def _sanitize_mermaid_line(line: str) -> str:
    line = line.replace('[\\"', '["').replace('\\"]', '"]')
    line = re.sub(r'\["([^"\]]+)\\+\]', r'["\1"]', line)
    if '["' in line and line.rstrip().endswith("]") and '"]' not in line:
        line = re.sub(r'\["(.+)\]$', r'["\1"]', line.rstrip())
    return line


def _sanitize_mermaid_source(source: str) -> str:
    return "\n".join(_sanitize_mermaid_line(line) for line in source.splitlines())


def _sanitize_mermaid_fences(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        block = match.group(0)
        inner = block[10:-3] if block.endswith("```") else block[10:]
        sanitized = _sanitize_mermaid_source(inner)
        return f"```mermaid{sanitized}\n```"

    return _MERMAID_FENCE_RE.sub(repl, text)


def _escape_pipes_in_math_segment(math: str) -> str:
    body = math[1:-1]
    return "$" + _UNESCAPED_PIPE_RE.sub(r"\\|", body) + "$"


def _escape_pipes_in_table_line(line: str) -> str:
    segments: list[str] = []
    cursor = 0
    for match in _INLINE_MATH_RE.finditer(line):
        segments.append(line[cursor : match.start()])
        segments.append(_escape_pipes_in_math_segment(match.group(0)))
        cursor = match.end()
    segments.append(line[cursor:])
    return "".join(segments)


def escape_pipes_in_table_math(text: str) -> str:
    """GFM 表格以 | 分列；$...$ 内的裸 | 会破坏列结构，需转义为 \\|。"""
    lines = text.split("\n")
    return "\n".join(
        _escape_pipes_in_table_line(line) if _TABLE_ROW_RE.match(line) else line
        for line in lines
    )


def escape_bare_underscores(text: str) -> str:
    """保护 $...$、围栏代码块外的伪 LaTeX 下划线，避免 Markdown 误解析为强调。"""
    parts: list[str] = []
    last = 0
    for match in _FENCE_RE.finditer(text):
        chunk = text[last : match.start()]
        parts.append(_escape_underscores_in_plain(chunk))
        parts.append(match.group(0))
        last = match.end()
    parts.append(_escape_underscores_in_plain(text[last:]))
    return "".join(parts)


def _escape_underscores_in_plain(text: str) -> str:
    segments: list[str] = []
    cursor = 0
    for match in _INLINE_MATH_RE.finditer(text):
        segments.append(_BARE_UNDERSCORE_RE.sub(r"\1\\_\2", text[cursor : match.start()]))
        segments.append(match.group(0))
        cursor = match.end()
    segments.append(_BARE_UNDERSCORE_RE.sub(r"\1\\_\2", text[cursor:]))
    return "".join(segments)


def sanitize_deep_read_body(body: str) -> str:
    text = body.strip()
    if not text:
        return text
    text = _sanitize_mermaid_fences(text)
    text = escape_bare_underscores(text)
    return text


def normalize_mermaid_source(source: str) -> str:
    """供前端 Mermaid 渲染前使用的引号规范化。"""
    return _sanitize_mermaid_source(source)
