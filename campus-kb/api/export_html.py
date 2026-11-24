"""把结构化草稿排成一段可直接粘进公众号编辑器的 HTML。

为什么不是直接给 Markdown：公众号后台的编辑器只认真实 HTML，且会把
`<style>` 标签和 class 全部剥掉，只留下内联 `style=""`。所以这里不写
样式表、不用 class，所有版式都落在标签自己身上，粘过去就是排好的样子。

几条取舍：
- 不渲染 `[A1]` 这类内部素材编号——那是给编辑核出处用的，发布稿不该出现；
- 「（素材不足，待补充）」整段跳过，只在整节都空时连小标题一起不出；
- 配图统一给虚线占位框（尺寸 + 图注），编辑按图注替换成现场照片；
- 只输出片段，不套 `<html><body>`，方便直接粘；下载完整文件由前端包一层。
"""

from __future__ import annotations

import html as _html
import re
from typing import Any

# 校色主色，只用在标题左侧竖线与分隔装饰上，正文保持中性灰
ACCENT = "#A6192E"

_EMPTY_PARA = re.compile(r"^[（(]\s*素材不足[,，]\s*待补充\s*[）)]$")


def _esc(text: Any) -> str:
    return _html.escape(str(text or ""), quote=False)


def _para(text: str) -> str:
    return (
        '<p style="margin:0 0 18px;font-size:16px;line-height:1.9;'
        'color:#3a3a3a;letter-spacing:0.4px;text-align:justify;">'
        f"{_esc(text)}</p>"
    )


def _heading(text: str) -> str:
    return (
        '<h2 style="margin:30px 0 14px;padding-left:9px;border-left:3px solid '
        f'{ACCENT};font-size:17.5px;line-height:1.55;font-weight:700;color:#1a1a1a;">'
        f"{_esc(text)}</h2>"
    )


def _figure_block(fig: dict) -> str:
    caption = _esc(fig.get("caption") or "")
    width = fig.get("width") or ""
    height = fig.get("height") or ""
    size = f"{width}×{height}" if width and height else ""
    hint = "请替换为对应现场照片"
    tail = f"{caption}　{size}" if caption else size
    return (
        '<section style="margin:22px 0;padding:34px 14px;border:1px dashed #cfcfcf;'
        "background:#fafafa;text-align:center;border-radius:4px;"
        'font-size:0;line-height:0;">'
        '<p style="margin:0 0 7px;font-size:14px;line-height:1.6;color:#9b9b9b;'
        f'letter-spacing:1px;">配图占位 · {_esc(hint)}</p>'
        '<p style="margin:0;font-size:12px;line-height:1.7;color:#b0b0b0;">'
        f"{tail}</p>"
        "</section>"
    )


def _figures_by_section(figures: list[dict] | None) -> dict[int, list[dict]]:
    grouped: dict[int, list[dict]] = {}
    for fig in figures or []:
        if not isinstance(fig, dict):
            continue
        idx = fig.get("sectionIndex")
        if not isinstance(idx, int):
            continue
        grouped.setdefault(idx, []).append(fig)
    return grouped


def article_to_html(article: dict, figures: list[dict] | None = None) -> str:
    """结构化草稿 → 公众号可直粘 HTML 片段（内联样式，无 class）。"""
    grouped = _figures_by_section(figures)
    parts: list[str] = ['<section style="padding:0 2px;">']

    title = str(article.get("title") or "").strip()
    if title:
        parts.append(
            '<h1 style="margin:0 0 10px;font-size:22px;line-height:1.45;font-weight:700;'
            f'color:#1a1a1a;text-align:center;letter-spacing:0.5px;">{_esc(title)}</h1>'
        )

    lead = str(article.get("lead") or "").strip()
    if lead:
        parts.append(
            '<p style="margin:0 0 22px;font-size:14.5px;line-height:1.75;color:#8c8c8c;'
            f'text-align:center;">{_esc(lead)}</p>'
        )

    sections = [s for s in (article.get("sections") or []) if isinstance(s, dict)]
    if title or lead:
        parts.append('<section style="height:1px;background:#ececec;margin:0 0 26px;"></section>')

    for index, section in enumerate(sections):
        paragraphs = [
            str(p.get("text") or "").strip()
            for p in (section.get("paragraphs") or [])
            if isinstance(p, dict)
        ]
        # 待补充的占位段不算正文：整节都是占位就连小标题一起不输出
        paragraphs = [t for t in paragraphs if t and not _EMPTY_PARA.match(t)]

        heading = str(section.get("heading") or "").strip()
        if heading and paragraphs:
            parts.append(_heading(heading))
        for text in paragraphs:
            parts.append(_para(text))
        for fig in grouped.get(index, []):
            parts.append(_figure_block(fig))

    parts.append("</section>")
    return "".join(parts) + "\n"
