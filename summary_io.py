"""生成 / 写入 Markdown 总结与 HTML 中转页。"""

from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import markdown

from zotero_links import TermLink, zotero_item_url, zotero_pdf_url


def slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", text, flags=re.UNICODE).strip("-")
    return (slug or "item")[:max_len]


def summary_paths(
    summaries_dir: Path,
    hubs_dir: Path,
    item_key: str,
    title: str,
) -> tuple[Path, Path]:
    summaries = summaries_dir
    hubs = hubs_dir
    summaries.mkdir(parents=True, exist_ok=True)
    hubs.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    name = f"{stamp}_{item_key}_{slugify(title)}"
    return summaries / f"{name}.md", hubs / f"{name}.html"


def file_uri(path: Path) -> str:
    return Path(path).resolve().as_uri()


def build_markdown(
    item: dict[str, Any],
    briefing: str,
    sections: list[dict[str, str]],
    term_links: list[TermLink],
    pdf_attach_key: str | None,
) -> str:
    data = item["data"]
    title = data.get("title", "无标题")
    item_key = item["key"]
    authors = ", ".join(
        f"{c.get('lastName', '')} {c.get('firstName', '')}".strip()
        for c in data.get("creators", [])
        if c.get("creatorType") == "author"
    ) or "未知作者"
    journal = data.get("publicationTitle") or data.get("proceedingsTitle") or "未知来源"
    year = (data.get("date") or "")[:4]
    abstract = (data.get("abstractNote") or "").strip()

    lines = [
        f"# {title}",
        "",
        f"> **头条简报**：{briefing}",
        "",
        f"- **作者**：{authors}",
        f"- **出处**：{journal} ({year or '未知年份'})",
        f"- **Zotero 条目**：<{zotero_item_url(item_key)}>",
        "",
    ]

    if abstract:
        lines.extend(["## 摘要", "", abstract, ""])

    lines.append("## 详细解读")
    lines.append("")
    for sec in sections:
        heading = sec.get("heading", "").strip()
        body = sec.get("body", "").strip()
        if heading:
            lines.append(f"### {heading}")
            lines.append("")
        if body:
            lines.append(body)
            lines.append("")

    lines.append("## 关键术语 · 原文定位")
    lines.append("")
    for link in term_links:
        source_note = {
            "annotation": "PDF 高亮注释",
            "fulltext": "PDF 全文检索",
            "item": "条目（未精确定位）",
        }.get(link.source, "")
        lines.append(f"- **[{link.term}]({link.url})** — {source_note}")
        if link.snippet:
            lines.append(f"  - 片段：{link.snippet}")
    lines.append("")

    lines.append("## 快捷入口")
    lines.append("")
    lines.append(f"- [在 Zotero 中打开条目]({zotero_item_url(item_key)})")
    if pdf_attach_key:
        lines.append(f"- [打开 PDF]({zotero_pdf_url(pdf_attach_key)})")
    lines.append("")
    lines.append(f"---\n*生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    return "\n".join(lines)


def build_hub_html(
    item: dict[str, Any],
    briefing: str,
    sections: list[dict[str, str]],
    term_links: list[TermLink],
    md_content: str,
    pdf_attach_key: str | None,
    note_id: str,
) -> str:
    data = item["data"]
    title = html.escape(data.get("title", "无标题"))
    item_key = item["key"]
    detail_html = markdown.markdown(
        md_content,
        extensions=["extra", "nl2br", "sane_lists"],
    )
    app_url = f"http://127.0.0.1:18765/note/{note_id}"

    section_html = ""
    for sec in sections[:3]:
        h = html.escape(sec.get("heading", ""))
        b = html.escape(sec.get("body", ""))
        if h or b:
            section_html += f"<div class='section'><h3>{h}</h3><p>{b}</p></div>"

    terms_html = ""
    for link in term_links:
        label = {
            "annotation": "注释定位",
            "fulltext": "全文页码",
            "item": "打开条目",
        }.get(link.source, "链接")
        terms_html += (
            f"<a class='term' href='{html.escape(link.url)}' title='{html.escape(link.snippet)}'>"
            f"{html.escape(link.term)} <span class='badge'>{label}</span></a>"
        )

    zotero_url = zotero_item_url(item_key)
    pdf_url = zotero_pdf_url(pdf_attach_key) if pdf_attach_key else ""

    pdf_btn = (
        f"<a class='btn secondary' href='{html.escape(pdf_url)}'>打开 PDF</a>"
        if pdf_url
        else ""
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} · 文献简报</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
           max-width: 720px; margin: 0 auto; padding: 24px 20px 40px; color: #1d1d1f; background: #f5f5f7; }}
    .card {{ background: #fff; border-radius: 14px; padding: 22px 24px; box-shadow: 0 2px 16px rgba(0,0,0,.06); }}
    h1 {{ font-size: 1.35rem; margin: 0 0 12px; line-height: 1.35; }}
    .brief {{ background: #f0f7ff; border-left: 4px solid #007aff; padding: 12px 14px;
              border-radius: 8px; margin: 14px 0 18px; line-height: 1.55; }}
    .actions {{ display: flex; flex-wrap: wrap; gap: 10px; margin: 18px 0; }}
    .btn {{ display: inline-block; padding: 10px 16px; border-radius: 10px; text-decoration: none;
            font-weight: 600; font-size: 14px; }}
    .btn.primary {{ background: #007aff; color: #fff; }}
    .btn.secondary {{ background: #e8e8ed; color: #1d1d1f; }}
    .section h3 {{ margin: 16px 0 6px; font-size: 1rem; }}
    .section p {{ margin: 0 0 10px; color: #3a3a3c; line-height: 1.6; white-space: pre-wrap; }}
    .terms {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }}
    .term {{ background: #f2f2f7; color: #007aff; padding: 8px 12px; border-radius: 999px;
             text-decoration: none; font-size: 13px; }}
    .badge {{ background: #007aff; color: #fff; font-size: 11px; padding: 2px 6px;
              border-radius: 6px; margin-left: 4px; }}
    h2 {{ font-size: 1rem; margin: 22px 0 8px; }}
    .hint {{ color: #86868b; font-size: 12px; margin-top: 20px; }}
    #detail {{ margin-top: 28px; padding-top: 24px; border-top: 1px solid #e5e5ea; }}
    #detail h2 {{ font-size: 1.1rem; margin: 0 0 16px; }}
    .detail-body {{ line-height: 1.65; font-size: 14px; color: #3a3a3c; }}
    .detail-body h2 {{ font-size: 1rem; margin: 20px 0 8px; color: #1d1d1f; }}
    .detail-body h3 {{ font-size: 0.95rem; margin: 14px 0 6px; }}
    .detail-body a {{ color: #007aff; }}
    .detail-body blockquote {{ margin: 0; padding: 10px 14px; background: #f9f9fb; border-left: 3px solid #007aff; }}
    .detail-body ul {{ padding-left: 1.2em; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>{title}</h1>
    <div class="brief">{html.escape(briefing)}</div>
    <div class="actions">
      <a class="btn primary" href="#detail">查看详细总结</a>
      <a class="btn secondary" href="{html.escape(zotero_url)}">在 Zotero 中打开原文</a>
      {pdf_btn}
      <a class="btn secondary" href="{html.escape(app_url)}" id="app-link" style="display:none">在应用中打开</a>
    </div>
    {section_html}
    <h2>关键术语 · 点击跳转原文定位</h2>
    <div class="terms">{terms_html or '<span class="hint">暂无术语链接</span>'}</div>
    <div id="detail">
      <h2>详细总结</h2>
      <div class="detail-body">{detail_html}</div>
    </div>
    <p class="hint">注释定位依赖你在 Zotero PDF 中的高亮；全文页码依赖 Zotero 已索引 PDF。</p>
  </div>
  <script>
    fetch("http://127.0.0.1:18765/api/status").then(r => r.ok && (
      document.getElementById('app-link').style.display = 'inline-block'
    )).catch(() => {{}});
  </script>
</body>
</html>"""


def parse_llm_summary(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
    if fence:
        raw = fence.group(1)
    else:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1:
            raw = raw[start : end + 1]
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    return {
        "briefing": raw[:200],
        "sections": [{"heading": "解读", "body": raw}],
        "key_terms": [],
    }


def write_outputs(
    summaries_dir: Path,
    hubs_dir: Path,
    item: dict[str, Any],
    briefing: str,
    sections: list[dict[str, str]],
    term_links: list[TermLink],
    pdf_attach_key: str | None,
) -> tuple[Path, Path]:
    title = item["data"].get("title", "无标题")
    md_path, hub_path = summary_paths(summaries_dir, hubs_dir, item["key"], title)
    note_id = md_path.stem
    md_content = build_markdown(item, briefing, sections, term_links, pdf_attach_key)
    md_path.write_text(md_content, encoding="utf-8")
    hub_path.write_text(
        build_hub_html(
            item, briefing, sections, term_links, md_content, pdf_attach_key, note_id
        ),
        encoding="utf-8",
    )
    return md_path, hub_path
