"""往期公众号推文档案（只读）。

元数据来自 corpus/wechat-sources.json（文章标题、发布日期、原文链接、字数、配图数），
正文摘要来自语料目录里的本地入库文本。两者都只读取，不修改语料。

Docker 中语料目录与 sources 文件分别挂进来，sources 位于 CAMPUS_CORPUS_DIR 的上一级；
本地开发时用仓库内默认路径。
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

from . import search as corpus_search

KB = Path(__file__).resolve().parent.parent
SOURCES = KB / "corpus" / "wechat-sources.json"
EXCERPT_LEN = 110
ARTICLE_LIMIT = 12000
_FILE_SAFE = re.compile(r"^[^\s/\\]{1,200}_WX\.txt$")
_IMAGE_LINE = re.compile(r"^\[图\d+\]$")


def _sources_path() -> Path:
    """显式指定语料目录时以它为准，不回退到仓库默认，避免混用两套语料。"""
    root = os.environ.get("CAMPUS_CORPUS_DIR")
    if root:
        return Path(root).parent / "wechat-sources.json"
    return SOURCES


def load_articles() -> list[dict[str, Any]]:
    """读取公众号元数据；文件缺失或损坏时返回空列表，不阻断页面。"""
    try:
        data = json.loads(_sources_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    items = data.get("articles", []) if isinstance(data, dict) else []
    return [
        item for item in items
        if isinstance(item, dict) and item.get("url") and item.get("published")
    ]


def _excerpt(file_name: str) -> str:
    """取入库正文开头几句做摘要：跳过首行标题与图片占位。"""
    if not _FILE_SAFE.fullmatch(file_name):
        return ""
    try:
        text = (corpus_search.corpus_dir() / file_name).read_text(
            encoding="utf-8", errors="replace"
        )
    except OSError:
        return ""

    picked: list[str] = []
    for line in text.splitlines()[1:]:
        line = line.strip()
        if not line or _IMAGE_LINE.fullmatch(line):
            continue
        picked.append(line)
        if sum(len(x) for x in picked) >= EXCERPT_LEN:
            break
    return " ".join(picked)[:EXCERPT_LEN]


def list_articles(query: str = "", month: str = "") -> dict[str, Any]:
    """按发布日期倒序列出推文；query 搜标题与正文，month 形如 2026-11。"""
    keyword = query.strip().lower()
    rows: list[dict[str, Any]] = []
    for item in load_articles():
        published = str(item.get("published", ""))
        if month and not published.startswith(month):
            continue
        file_name = str(item.get("file", ""))
        excerpt = _excerpt(file_name)
        title = str(item.get("title", ""))
        if keyword and keyword not in title.lower() and keyword not in excerpt.lower():
            continue
        rows.append({
            "title": title,
            "url": str(item["url"]),
            "published": published,
            "month": published[:7],
            "file": file_name,
            "excerpt": excerpt,
            "chars": int(item.get("chars") or 0),
            "images": int(item.get("images") or 0),
        })

    rows.sort(key=lambda row: row["published"], reverse=True)
    # 月份选项始终基于全量数据：下拉筛选后才不会让其它月份从选项里消失。
    all_counts = Counter(
        str(item.get("published", ""))[:7]
        for item in load_articles()
    )
    return {
        "total": len(rows),
        "months": [
            {"month": key, "count": all_counts[key]}
            for key in sorted(all_counts, reverse=True)
            if key
        ],
        "articles": rows,
        "query": query,
        "month": month,
    }


def article_detail(file_name: str) -> dict[str, Any]:
    """单篇入库正文，供页面内预览；文件名严格白名单，杜绝路径穿越。"""
    if not _FILE_SAFE.fullmatch(file_name):
        raise ValueError("非法文章文件名")
    try:
        text = (corpus_search.corpus_dir() / file_name).read_text(
            encoding="utf-8", errors="replace"
        )
    except OSError as exc:
        raise LookupError("知识库中没有这篇文章的入库正文") from exc

    meta = next((x for x in load_articles() if x.get("file") == file_name), {})
    return {
        "title": str(meta.get("title", file_name.removesuffix("_WX.txt"))),
        "published": str(meta.get("published", "")),
        "url": str(meta.get("url", "")),
        "file": file_name,
        "text": text[:ARTICLE_LIMIT],
        "truncated": len(text) > ARTICLE_LIMIT,
    }
