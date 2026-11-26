"""语料库检索：段落分块 + BM25 + 本地 embedding 混合召回（实现见 rag.py）。

体量决定方案：corpus/text/ 约 628KB / 50 个文件，切成数百个段落块后，
内存里做 BM25 + 稠密向量检索足够快，不需要外部向量数据库。
出处（文件名 + 起止行号）随每个块一路带到前端、Agent 与文章生成。

兼容：search() 的返回结构保留 query/total/scanned/results 与每项的
file/line/excerpt/hits，新增 endLine/score/similarity/matchedBy/retrieval。
mode=strict 可复现旧的「多词 AND + 行级命中」行为，用于回归对照与回滚。

语料可见范围（scope）：
- public（默认）：排除 `*_DOCUMENT.txt` 内部档案，只用公开推文与通用语料。
  成稿、Agent 问答与公开 /api/search 都走这一档，避免把行程、采购论证、
  手机号等内部信息写进公众号文章。
- all：显式包含内部档案，仅供内部核查使用（/api/search?scope=all）。
两档的语料版本戳与向量索引按 scope 隔离，不会互相覆盖。
"""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from . import rag

KB = Path(__file__).resolve().parent.parent

SCOPE_PUBLIC = "public"  # 默认：公开推文 + 通用语料，排除内部档案
SCOPE_ALL = "all"        # 显式：包含 *_DOCUMENT.txt 内部档案
INTERNAL_SUFFIX = "_DOCUMENT.txt"

# 给两档范围不同的版本戳偏置，保证向量索引文件名不重叠：
# 内部档案变动不应让公开检索的缓存失效并重建索引，反之亦然。
_SCOPE_STAMP_OFFSET = {SCOPE_PUBLIC: 0, SCOPE_ALL: 1}


@dataclass(frozen=True)
class Doc:
    name: str  # 文件名（去扩展名），即语料条目 ID
    text: str


def _check_scope(scope: str) -> str:
    if scope not in _SCOPE_STAMP_OFFSET:
        raise ValueError(f"未知检索范围 scope={scope!r}，应为 {SCOPE_PUBLIC} 或 {SCOPE_ALL}")
    return scope


def _is_internal(name: str) -> bool:
    return name.endswith(INTERNAL_SUFFIX)


def corpus_dir() -> Path:
    override = os.environ.get("CAMPUS_CORPUS_DIR")
    return Path(override) if override else KB / "corpus" / "text"


def _corpus_stamp(root: Path, scope: str = SCOPE_PUBLIC) -> int:
    """按可见范围分别计算版本戳：内部档案变动不惊动公开检索的缓存与索引。"""
    _check_scope(scope)
    try:
        stamp = max(
            (
                p.stat().st_mtime_ns
                for p in root.glob("*.txt")
                if scope == SCOPE_ALL or not _is_internal(p.name)
            ),
            default=0,
        )
    except OSError:
        stamp = 0
    # 乘 2 再偏置：public 恒为偶数、all 恒为奇数，两档索引文件名绝不重叠。
    return stamp * 2 + _SCOPE_STAMP_OFFSET[scope]


def load_corpus(root: str, scope: str = SCOPE_PUBLIC) -> tuple[Doc, ...]:
    """root 参与缓存 key：测试时可注入临时目录。

    带上版本戳，新增或修改语料后无需重启进程即可检索到——抓完文章立刻可用。
    scope 默认只装公开语料；内部档案须显式 scope="all" 才纳入。
    """
    return _load_corpus(root, _corpus_stamp(Path(root), scope), scope)


@lru_cache(maxsize=16)
def _load_corpus(root: str, stamp: int, scope: str) -> tuple[Doc, ...]:
    docs = []
    for p in sorted(Path(root).glob("*.txt")):
        if scope != SCOPE_ALL and _is_internal(p.name):
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        if text.strip():
            docs.append(Doc(name=p.stem, text=text))
    return tuple(docs)


def search(
    query: str,
    root: str | None = None,
    limit: int = 20,
    mode: str = "hybrid",
    scope: str = SCOPE_PUBLIC,
) -> dict:
    """检索语料库，返回带文件名 + 行号出处的片段。

    mode: hybrid（默认，BM25 + 语义向量 RRF 融合）/ keyword（仅 BM25）/
          semantic（仅向量，模型不可用自动降级）/ strict（旧 AND 行为）。
    scope: public（默认，排除内部档案）/ all（显式包含，仅供内部核查）。
    """
    _check_scope(scope)
    root_path = str(Path(root)) if root else str(corpus_dir())
    stamp = _corpus_stamp(Path(root_path), scope)
    docs = load_corpus(root_path, scope)
    results = rag.hybrid_search(
        query, docs, root=root_path, stamp=stamp, mode=mode, limit=limit
    )
    return {
        "query": query,
        "total": len(results),
        "scanned": len(docs),
        "mode": mode,
        "scope": scope,
        "retrieval": rag.status(docs, stamp, root_path),
        "results": results,
    }
