"""把顺序 id 时代的标注迁到内容哈希 id（一次性）。

背景：`build_figure_index.py` 原来用 `f0001…` 顺序编号，文件夹按文章名排序，
新抓一批推文插进中间，后面所有 id 整体位移，`captions.json` 的标注就错位到
别的图上了。改成内容哈希 id 后，需要把旧索引里那批标注按「文件字节」重新认领
一次：哈希算出来是什么 id，标注就挂到什么 id 上。

幂等：重复跑结果一样，已有 captions.json 的其它条目原样保留。

用法：
    uv run python tools/migrate_captions.py            # 迁移
    uv run python tools/migrate_captions.py --dry-run  # 只看会迁多少条
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

IMAGES = Path(__file__).resolve().parent.parent / "corpus" / "images"
INDEX = IMAGES / "INDEX.json"
CAPTIONS = IMAGES / "captions.json"
ID_HEX = 10


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只统计，不写文件")
    args = ap.parse_args(argv)

    index = json.loads(INDEX.read_text(encoding="utf-8"))
    captions = json.loads(CAPTIONS.read_text(encoding="utf-8")) if CAPTIONS.exists() else {}

    migrated = already = missing = skipped = 0
    for item in index.get("images", []):
        if not item.get("caption") or item.get("kind") in (None, "", "unknown"):
            skipped += 1
            continue
        path = IMAGES / item["article"] / item["file"]
        if not path.is_file():
            missing += 1
            print(f"  ✗ 文件不在：{item['article']}/{item['file']}")
            continue
        digest = item.get("digest") or hashlib.sha1(path.read_bytes()).hexdigest()
        fid = f"f{digest[:ID_HEX]}"
        if fid in captions:
            already += 1
            continue
        captions[fid] = {"caption": item["caption"], "kind": item["kind"]}
        migrated += 1

    print(f"迁移 {migrated} 条、已存在 {already} 条、无标注跳过 {skipped}、文件缺失 {missing}")
    if args.dry_run:
        print("（--dry-run，未写文件）")
        return 0
    CAPTIONS.write_text(
        json.dumps(dict(sorted(captions.items())), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"写入 {CAPTIONS.relative_to(IMAGES.parent.parent)}，共 {len(captions)} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
