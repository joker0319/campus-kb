"""配图推荐：从往期推文的真实照片里，给成稿的每一节找能用的图。

语料里的图是整篇扒下来的，同一篇推文里混着实拍、合影、榜单截图、二维码、
招生长图的「PART 1/2/3」分段页。直接按文章相关度推，用户点开十次有七次是二维码，
所以这里先按图像性质筛，再按文字相关度排。

两条硬规则：
1. `portrait`（真实师生单人肖像）不进推荐——公众号发别人照片涉及肖像权，留给编辑自己决定；
2. 分数不达阈值的段落宁可不配图，也不拿不相关的图凑数（absence 比 noise 好）。
"""

from __future__ import annotations

import json
import math
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Sequence

from .rag import tokenize

CORPUS = Path(__file__).resolve().parent.parent / "corpus"
IMAGES = CORPUS / "images"
INDEX = IMAGES / "INDEX.json"

# 图像性质权重：实景最能说明现场，合影次之，榜单截图只适合数据段落。
# 海报权重压得较低但不判死——「心理咨询预约信息卡」这类长图，在讲服务的段落里
# 恰恰是最合适的配图，权重给 0 会把它们一起误杀。
KIND_WEIGHT = {"scene": 1.0, "crowd": 0.9, "chart": 0.75, "poster": 0.65}
# 单人肖像、纯文字分段页、二维码、logo 一律不推。
SKIP_KINDS = {"portrait", "slide", "qr", "icon", "unknown"}

MIN_SCORE = 0.5  # 低于此分视为「没有合适的图」，宁可空着
# 图注与段落至少共享两个 2-gram 才算真命中。只共享一个（例如都出现「全国」）
# 太容易误判：会议报道的段落会把同一篇推文里的「机器人队合影」认成相关图。
EXACT_MIN_SHARED = 2
DEFAULT_PER_SECTION = 2


class FigureIndexMissing(RuntimeError):
    """索引还没建，提示跑 tools/build_figure_index.py。"""


def _load() -> tuple[dict, ...]:
    if not INDEX.exists():
        raise FigureIndexMissing("配图索引不存在，请先在 campus-kb 下执行 uv run python tools/build_figure_index.py")
    data = json.loads(INDEX.read_text(encoding="utf-8"))
    return tuple(item for item in data.get("images", []) if item.get("kind") not in SKIP_KINDS)


@lru_cache(maxsize=1)
def _cached(stamp: float) -> tuple[dict, ...]:
    return _load()


def _images() -> tuple[dict, ...]:
    stamp = INDEX.stat().st_mtime if INDEX.exists() else 0.0
    return _cached(stamp)


def available() -> int:
    try:
        return len(_images())
    except FigureIndexMissing:
        return 0


@lru_cache(maxsize=4096)
def _terms(text: str) -> frozenset[str]:
    return frozenset(tokenize(text))


def _score(section_text: str, heading: str, item: dict) -> tuple[float, bool]:
    """返回（分数，图注是否真的有交集）。

    图注相关度占七成、来源文章相关度占三成。来源标题的权重必须低且要能被识别：
    同一篇推文里的所有图都会沾到标题的光，若不区分，一篇会议报道的段落会推出
    那篇推文里的「机器人队合影」。第二个返回值就是用来把这类「只靠标题蹭到分」的
    图单独标出来，前端提示人工确认，而不是当真命中的图推给用户。
    """
    body = _terms(f"{heading} {section_text}")
    if not body:
        return (0.0, False)
    caption = _terms(item.get("caption", ""))
    title = _terms(item.get("title", ""))

    shared = len(body & caption)
    cap_hit = shared / math.sqrt(len(caption)) if caption else 0.0
    title_hit = len(body & title) / math.sqrt(len(title)) if title else 0.0
    raw = 0.7 * cap_hit + 0.3 * title_hit
    return (raw * KIND_WEIGHT.get(item.get("kind", "unknown"), 0.0), shared >= EXACT_MIN_SHARED)


def _row(item: dict, section_index: int, heading: str, score: float, weak: bool) -> dict:
    return {
        "id": item["id"],
        "url": f"/api/figure/{item['id']}",
        "caption": item.get("caption") or "往期推文配图",
        "kind": item.get("kind", "unknown"),
        "width": item.get("w", 0),
        "height": item.get("h", 0),
        "sourceTitle": item.get("title", ""),
        "sourcePublished": item.get("published", ""),
        "sectionIndex": section_index,
        "sectionHeading": heading,
        "score": round(score, 3),
        "weak": weak,
    }


def recommend(
    sections: Sequence[dict],
    *,
    per_section: int = DEFAULT_PER_SECTION,
    min_score: float = MIN_SCORE,
) -> list[dict]:
    """给每一节挑图；全篇不重复用同一张，避免一篇文章里同一张图出现两次。

    只靠标题蹭到分的图（weak）不进正式推荐；整节一张对得上的都没有时，
    才补一张 weak 并标注，让编辑知道「有关联但需自己确认」，而不是空着或硬凑。
    """
    images = _images()
    used: set[str] = set()
    picked: list[dict] = []

    for index, section in enumerate(sections):
        heading = str(section.get("heading", "")).strip()
        text = " ".join(str(p.get("text", "")) for p in section.get("paragraphs", []))
        if not text.strip() and not heading.strip():
            continue

        strong: list[tuple[float, dict]] = []
        weak: list[tuple[float, dict]] = []
        for item in images:
            if item["id"] in used:
                continue
            score, exact = _score(text, heading, item)
            if score < min_score:
                continue
            (strong if exact else weak).append((score, item))

        strong.sort(key=lambda pair: -pair[0])
        chosen = [(score, item, False) for score, item in strong[:per_section]]
        if not chosen and weak:
            weak.sort(key=lambda pair: -pair[0])
            chosen = [(weak[0][0], weak[0][1], True)]

        for score, item, is_weak in chosen:
            used.add(item["id"])
            picked.append(_row(item, index, heading, score, is_weak))

    return picked


@lru_cache(maxsize=2)
def _paths(stamp: float) -> dict[str, Path]:
    """id → 文件路径。每张图要走一次这个查询，不能每次重读索引。"""
    if not INDEX.exists():
        return {}
    data = json.loads(INDEX.read_text(encoding="utf-8"))
    out: dict[str, Path] = {}
    for item in data.get("images", []):
        out[item["id"]] = IMAGES / item["article"] / item["file"]
    return out


def resolve(figure_id: str) -> Path | None:
    """按 id 找到文件真身，供接口下发；找不到返回 None（前端显示占位）。"""
    stamp = INDEX.stat().st_mtime if INDEX.exists() else 0.0
    path = _paths(stamp).get(figure_id)
    return path if path is not None and path.is_file() else None


def kind_stats() -> Counter:
    """给文档/自检用：各类图有多少张。"""
    return Counter(item.get("kind", "unknown") for item in _images())


def iter_all() -> Iterable[dict]:
    return _images()
