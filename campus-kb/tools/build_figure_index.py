"""扫 corpus/images 建配图索引。

语料里的图是从往期推文整篇扒下来的原图，按《图1.jpg、图2.png…》编号，
只保留了「哪篇文章的第几张」，没有任何图像内容信息。成稿时想推荐真图，
至少要有两样东西：稳定 id（给前端拼 URL）和一句话描述（用来和正文段落匹配）。

这个脚本负责前面那半：过滤掉分隔线/图标/二维码这类不能当配图的碎图，
按文章归组，落一份 INDEX.json。描述由 tools/make_contact_sheets.py + 人工/视觉
识别产出，写进 captions.json，最后由 api/figures.py 合并。

id 用**内容哈希**（`f` + sha1 前 10 位），不用顺序号。顺序号曾经害过一次：
文件夹按文章名排序，新抓一批推文插进中间，后面所有 id 整体位移，已经标注好的
captions 全部错位到别的图上。内容哈希只跟图片字节走，重建多少次都不变。

用法：
    uv run python tools/build_figure_index.py
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from PIL import Image

CORPUS = Path(__file__).resolve().parent.parent / "corpus"
IMAGES = CORPUS / "images"
SOURCES = CORPUS / "wechat-sources.json"
OUT = IMAGES / "INDEX.json"
CAPTIONS = IMAGES / "captions.json"   # id → {caption, kind}，由 apply_captions.py 写

# id 取 sha1 前 10 位：692 张图碰撞概率约 1e-4，够用且 URL 短。
ID_HEX = 10

# 公众号正文里混着大量分隔线、图标、二维码占位：1080x92 的横条、400x400 的 1KB 方块、
# 动图表情。这些尺寸/体积阈值是从 657 张实际文件里统计出来的，宁可漏掉边缘图，
# 也不要把不能当配图的图推给用户。
MIN_W, MIN_H, MIN_KB = 600, 400, 40
SKIP_EXT = {".gif"}


def load_titles() -> dict[str, dict]:
    """folder 名 → 文章标题与发布日期（folder 名就是文件名去扩展名）。"""
    if not SOURCES.exists():
        return {}
    data = json.loads(SOURCES.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for art in data.get("articles", []):
        stem = Path(art.get("file", "")).stem
        if stem:
            out[stem] = {
                "title": art.get("title") or stem,
                "published": art.get("published") or "",
                "url": art.get("url") or "",
            }
    return out


def natural_key(path: Path) -> tuple[int, str]:
    """图2 要排在图10 前面，所以按数字排而不是按字符串。"""
    digits = "".join(ch for ch in path.stem if ch.isdigit())
    return (int(digits) if digits else 0, path.name)


def figure_id(digest: str) -> str:
    return f"f{digest[:ID_HEX]}"


def load_captions() -> dict[str, dict]:
    """已标注的描述：id → {caption, kind}。没有就返回空，全库按未标注处理。"""
    if not CAPTIONS.exists():
        return {}
    return json.loads(CAPTIONS.read_text(encoding="utf-8"))


def main() -> None:
    titles = load_titles()
    captions = load_captions()
    folders = sorted(p for p in IMAGES.iterdir() if p.is_dir() and not p.name.startswith("."))

    images: list[dict] = []
    seen_hash: dict[str, str] = {}
    dropped = {"small": 0, "gif": 0, "dup": 0, "broken": 0}
    labelled = 0

    for folder in folders:
        meta = titles.get(folder.name, {})
        for path in sorted(folder.iterdir(), key=natural_key):
            if not path.is_file():
                continue
            if path.suffix.lower() in SKIP_EXT:
                dropped["gif"] += 1
                continue
            try:
                with Image.open(path) as im:
                    w, h = im.size
                    fmt = im.format
            except Exception:
                dropped["broken"] += 1
                continue
            kb = path.stat().st_size // 1024
            if w < MIN_W or h < MIN_H or kb < MIN_KB or fmt == "GIF":
                dropped["small"] += 1
                continue

            digest = hashlib.sha1(path.read_bytes()).hexdigest()
            if digest in seen_hash:
                dropped["dup"] += 1
                continue
            seen_hash[digest] = path.name

            fid = figure_id(digest)
            cap = captions.get(fid, {})
            if cap.get("kind"):
                labelled += 1

            images.append(
                {
                    "id": fid,
                    "digest": digest,
                    "article": folder.name,
                    "title": meta.get("title", folder.name),
                    "published": meta.get("published", ""),
                    "url": meta.get("url", ""),
                    "file": path.name,
                    "w": w,
                    "h": h,
                    "kb": kb,
                    "caption": cap.get("caption", ""),
                    "kind": cap.get("kind", "unknown"),
                }
            )

    payload = {
        "version": 2,
        "builtAt": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "rule": f"宽>={MIN_W} 高>={MIN_H} 体积>={MIN_KB}KB，去动图与重复图；id=f+sha1[0:{ID_HEX}]",
        "images": images,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    by_article: dict[str, int] = {}
    for item in images:
        by_article[item["article"]] = by_article.get(item["article"], 0) + 1

    print(f"合格配图 {len(images)} 张 / {len(by_article)} 篇文章")
    print(f"过滤：碎图 {dropped['small']}、动图 {dropped['gif']}、重复 {dropped['dup']}、损坏 {dropped['broken']}")
    print(f"已标注 {labelled} 张，待标注 {len(images) - labelled} 张")
    print(f"写入 {OUT.relative_to(CORPUS.parent)}")


if __name__ == "__main__":
    main()
