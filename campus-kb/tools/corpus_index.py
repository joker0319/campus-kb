#!/usr/bin/env python3
"""按 corpus/wechat-sources.json 重新生成 INDEX.md 的「06-公众号推文」章节。

清单是抓取结果的投影，手写必然和实际脱节（加一批就漏一批），这里从元数据
直接生成表格。只替换 06 章节，其余章节原样保留。
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "corpus/INDEX.md"
SOURCES = ROOT / "corpus/wechat-sources.json"
HEAD = "## 06-公众号推文"


def build_section(items: list[dict]) -> str:
    items = sorted(items, key=lambda i: i["published"], reverse=True)
    total_chars = sum(int(i["chars"]) for i in items)
    ocr = [i for i in items if int(i.get("ocr", 0)) > 0]
    span = f"{items[-1]['published']} ~ {items[0]['published']}" if items else "—"

    lines = [
        f"{HEAD}（本地抓取，{len(items)} 篇）",
        "",
        "用 `campus-kb/tools/fetch_wechat.py` 从自有公众号抓取，正文落在 `corpus/text/*_WX.txt`",
        "（`_WX` 后缀标记来源），元数据在 `corpus/wechat-sources.json`，图片在 `corpus/images/<标题>/`。",
        "与上面五类档案一样只存本地，不进 git。",
        "",
        f"按发布日期倒序，共 {len(items)} 篇、约 {total_chars / 10000:.1f} 万字，"
        f"覆盖 {span}。其中 {len(ocr)} 篇为长图型需 Vision OCR，其余正文均在 HTML 里直接提取。",
        "",
        "| 文件 | 发布日期 | 字数 | 处理方式 |",
        "| --- | --- | --- | --- |",
    ]
    for i in items:
        way = "长图型，Vision OCR" if int(i.get("ocr", 0)) > 0 else "HTML 直取"
        title = i["title"].replace("|", "\\|")
        lines.append(f"| {title} | {i['published']} | {i['chars']} | {way} |")
    lines += [
        "",
        "抓取时会截断正文末尾的「推荐阅读 / 点击关注」卡片：长图末尾这类卡片会把**别的",
        "文章标题**一起 OCR 进来，造成 A 文里搜到 B 文标题的跨文档污染（见 `truncate_tail`）。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    data = json.loads(SOURCES.read_text(encoding="utf-8"))
    items = next(iter(data.values()))
    text = INDEX.read_text(encoding="utf-8")

    start = text.index(HEAD)
    # 章节到下一个二级标题或文件末尾
    rest = text[start + len(HEAD) :]
    nxt = rest.find("\n## ")
    end = len(text) if nxt == -1 else start + len(HEAD) + nxt + 1

    new = text[:start] + build_section(items) + text[end:]
    INDEX.write_text(new, encoding="utf-8")
    print(f"INDEX.md 已更新：{len(items)} 篇推文")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
