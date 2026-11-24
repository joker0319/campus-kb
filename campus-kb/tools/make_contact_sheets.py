"""把配图索引拼成带编号的九宫格，供视觉识别逐格打描述。

一次让模型看九张图，比逐张调 177 次省得多；代价是格子小，所以格子内只留
大号编号、不放文件名，描述也只要一句话。产出写进 sheet-map.json，
描述由调用方填进 captions.raw.json，再由 apply_captions.py 落到 captions.json。

只给**未标注**的图拼图：已标注的（captions.json 里有 id）跳过，这样每抓一批
新推文只需再拼几张，不用把 600 多张重看一遍。sheet 编号接着已有编号往下排，
sheet-map.json 是累加的，旧拼图的对应关系不会丢。

用法：
    uv run python tools/make_contact_sheets.py           # 只拼未标注的
    uv run python tools/make_contact_sheets.py --all     # 全部重拼（慎用，会覆盖映射）
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

IMAGES = Path(__file__).resolve().parent.parent / "corpus" / "images"
INDEX = IMAGES / "INDEX.json"
CAPTIONS = IMAGES / "captions.json"
OUT_DIR = IMAGES / ".sheets"
MAP = OUT_DIR / "sheet-map.json"

CELL_W, CELL_H = 480, 360
COLS, ROWS = 3, 3
PER_SHEET = COLS * ROWS
FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def fit(img: Image.Image, w: int, h: int) -> Image.Image:
    """等比缩到格子里，留白居中，避免拉伸变形让人误判画面。"""
    img = img.convert("RGB")
    scale = min(w / img.width, h / img.height)
    size = (max(1, int(img.width * scale)), max(1, int(img.height * scale)))
    resized = img.resize(size, Image.LANCZOS)
    canvas = Image.new("RGB", (w, h), "white")
    canvas.paste(resized, ((w - size[0]) // 2, (h - size[1]) // 2))
    return canvas


def next_sheet_no(mapping: dict[str, list[dict]]) -> int:
    """已有 sheet-07 就从不 08 开始，避免覆盖之前标注过的对应关系。"""
    nums = [int(m.group(1)) for name in mapping if (m := re.match(r"sheet-(\d+)", name))]
    return max(nums, default=0) + 1


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="全部重拼，忽略已标注状态")
    args = ap.parse_args(argv)

    data = json.loads(INDEX.read_text(encoding="utf-8"))
    captions = json.loads(CAPTIONS.read_text(encoding="utf-8")) if CAPTIONS.exists() else {}
    mapping: dict[str, list[dict]] = (
        json.loads(MAP.read_text(encoding="utf-8")) if MAP.exists() else {}
    )

    items = data["images"] if args.all else [i for i in data["images"] if i["id"] not in captions]
    if args.all:
        mapping = {}

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    font = load_font(44)
    start_no = next_sheet_no(mapping)

    for start in range(0, len(items), PER_SHEET):
        batch = items[start : start + PER_SHEET]
        sheet = Image.new("RGB", (CELL_W * COLS, CELL_H * ROWS), "white")
        draw = ImageDraw.Draw(sheet)
        cells = []
        for i, item in enumerate(batch):
            r, c = divmod(i, COLS)
            x, y = c * CELL_W, r * CELL_H
            with Image.open(IMAGES / item["article"] / item["file"]) as im:
                sheet.paste(fit(im, CELL_W - 12, CELL_H - 12), (x + 6, y + 6))
            draw.rectangle([x + 10, y + 10, x + 66, y + 60], fill="black")
            draw.text((x + 20, y + 12), str(i + 1), font=font, fill="white")
            draw.rectangle([x, y, x + CELL_W - 1, y + CELL_H - 1], outline="#cccccc")
            cells.append(
                {"cell": i + 1, "id": item["id"], "article": item["article"], "file": item["file"]}
            )

        name = f"sheet-{start_no + start // PER_SHEET:02d}.jpg"
        sheet.save(OUT_DIR / name, quality=86)
        mapping[name] = cells

    MAP.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"新拼 {len(range(0, len(items), PER_SHEET))} 张，覆盖未标注 {len(items)} 张配图")
    print(f"sheet-map 现有 {len(mapping)} 张拼图")
    print(f"输出目录 {OUT_DIR}")


if __name__ == "__main__":
    main()
