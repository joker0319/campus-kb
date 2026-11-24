"""把人工/视觉标注的描述合并进配图索引。

描述是按「拼图第几张第几格」记的（captions.raw.json），索引里是稳定 id，
这里靠 sheet-map.json 的对应关系回填，避免手抄 id 出错。
"""

from __future__ import annotations

import json
from pathlib import Path

IMAGES = Path(__file__).resolve().parent.parent / "corpus" / "images"
INDEX = IMAGES / "INDEX.json"
RAW = IMAGES / "captions.raw.json"
MAP = IMAGES / ".sheets" / "sheet-map.json"

KINDS = {"scene", "crowd", "chart", "poster", "portrait", "qr", "icon", "slide"}


def main() -> None:
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    mapping = json.loads(MAP.read_text(encoding="utf-8"))

    by_id: dict[str, dict] = {}
    for sheet, cells in raw.items():
        if sheet.startswith("_"):
            continue
        sheet_cells = mapping.get(sheet, [])
        if len(cells) != len(sheet_cells):
            raise SystemExit(f"{sheet} 标注 {len(cells)} 格，实际 {len(sheet_cells)} 格，对不上")
        for cell, meta in zip(sheet_cells, cells):
            kind = meta.get("kind", "").strip()
            if kind not in KINDS:
                raise SystemExit(f"{sheet} 第 {cell['cell']} 格 kind 非法：{kind}")
            by_id[cell["id"]] = {"caption": meta.get("caption", "").strip(), "kind": kind}

    missing = [item["id"] for item in index["images"] if item["id"] not in by_id]
    for item in index["images"]:
        meta = by_id.get(item["id"], {})
        item["caption"] = meta.get("caption", "")
        item["kind"] = meta.get("kind", "unknown")

    INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    counts: dict[str, int] = {}
    for item in index["images"]:
        counts[item["kind"]] = counts.get(item["kind"], 0) + 1
    print("分类统计：", "、".join(f"{k} {v}" for k, v in sorted(counts.items(), key=lambda x: -x[1])))
    print(f"共 {len(index['images'])} 张，未标注 {len(missing)} 张")


if __name__ == "__main__":
    main()
