"""把人工/视觉标注的描述合并进配图标注库。

描述是按「拼图第几张第几格」记的（captions.raw.json），图库用的是内容哈希 id，
这里靠 sheet-map.json 的对应关系回填，避免手抄 id 出错。结果落到 captions.json
（id → {caption, kind}），再调 build_figure_index 重建 INDEX.json。

累加式：只覆盖本轮出现过的 id，之前批次的标注原样保留，所以可以分多批标注、
每批跑一次，不用一次看完 600 多张。

用法：
    uv run python tools/apply_captions.py
    uv run python tools/apply_captions.py --no-index   # 只更新 captions.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_figure_index import main as rebuild_index

IMAGES = Path(__file__).resolve().parent.parent / "corpus" / "images"
CAPTIONS = IMAGES / "captions.json"
RAW = IMAGES / "captions.raw.json"
MAP = IMAGES / ".sheets" / "sheet-map.json"

KINDS = {"scene", "crowd", "chart", "poster", "portrait", "qr", "icon", "slide", "unknown"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-index", action="store_true", help="只写 captions.json，不重建索引")
    args = ap.parse_args(argv)

    raw = json.loads(RAW.read_text(encoding="utf-8"))
    mapping = json.loads(MAP.read_text(encoding="utf-8"))
    captions = json.loads(CAPTIONS.read_text(encoding="utf-8")) if CAPTIONS.exists() else {}
    index = json.loads((IMAGES / "INDEX.json").read_text(encoding="utf-8"))
    live = {item["id"] for item in index.get("images", [])}

    added = replaced = stale = 0
    for sheet, cells in raw.items():
        if sheet.startswith("_"):
            continue
        sheet_cells = mapping.get(sheet)
        if not sheet_cells:
            raise SystemExit(f"{sheet} 在 sheet-map.json 里找不到，先跑 make_contact_sheets.py")
        if len(cells) != len(sheet_cells):
            raise SystemExit(f"{sheet} 标注 {len(cells)} 格，实际 {len(sheet_cells)} 格，对不上")
        for cell, meta in zip(sheet_cells, cells):
            if cell["id"] not in live:
                # 顺序 id 时代的老拼图还会留在这里，其 id 已不在索引里；跳过而不是写进去
                stale += 1
                continue
            kind = str(meta.get("kind", "")).strip()
            if kind not in KINDS:
                raise SystemExit(f"{sheet} 第 {cell['cell']} 格 kind 非法：{kind!r}")
            if kind == "unknown" and not str(meta.get("caption", "")).strip():
                continue  # 空格子（拼图末尾不足九张）不占位
            existed = cell["id"] in captions
            captions[cell["id"]] = {
                "caption": str(meta.get("caption", "")).strip(),
                "kind": kind,
            }
            replaced += existed
            added += not existed

    # 索引里已经没有的 id（被过滤/去重掉）留着只会误导后来的标注
    pruned = [fid for fid in captions if fid not in live]
    for fid in pruned:
        del captions[fid]

    CAPTIONS.write_text(
        json.dumps(dict(sorted(captions.items())), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"captions.json：新增 {added} 条、更新 {replaced} 条、清理失效 {len(pruned)} 条，共 {len(captions)} 条")
    if stale:
        print(f"跳过 {stale} 格（老拼图里的顺序 id，已不在索引中）")

    if not args.no_index:
        rebuild_index()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
