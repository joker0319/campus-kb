"""语料库检索：段落分块 + BM25 + 本地 embedding 混合召回（实现见 rag.py）。

体量决定方案：corpus/text/ 约 628KB / 50 个文件，切成数百个段落块后，
内存里做 BM25 + 稠密向量检索足够快，不需要外部向量数据库。
出处（文件名 + 起止行号）随每个块一路带到前端、Agent 与文章生成。

兼容：search() 的返回结构保留 query/total/scanned/results 与每项的
file/line/excerpt/hits，新增 endLine/score/similarity/matchedBy/retrieval。
mode=strict 可复现旧的「多词 AND + 行级命中」行为，用于回归对照与回滚。
"""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from . import rag

KB = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Doc:
    name: str  # 文件名（去扩展名），即语料条目 ID
    text: str


def corpus_dir() -> Path:
    override = os.environ.get("CAMPUS_CORPUS_DIR")
    return Path(override) if override else KB / "corpus" / "text"


def _corpus_stamp(root: Path) -> int:
    """语料目录版本戳：任一文件新增或改动都会变，用来让缓存与向量索引失效。"""
    try:
        return max((p.stat().st_mtime_ns for p in root.glob("*.txt")), default=0)
    except OSError:
        return 0


def load_corpus(root: str) -> tuple[Doc, ...]:
    """root 参与缓存 key：测试时可注入临时目录。

    带上版本戳，新增或修改语料后无需重启进程即可检索到——抓完文章立刻可用。
    """
    return _load_corpus(root, _corpus_stamp(Path(root)))


@lru_cache(maxsize=8)
def _load_corpus(root: str, stamp: int) -> tuple[Doc, ...]:
    docs = []
    for p in sorted(Path(root).glob("*.txt")):
        text = p.read_text(encoding="utf-8", errors="replace")
        if text.strip():
            docs.append(Doc(name=p.stem, text=text))
    return tuple(docs)


def search(query: str, root: str | None = None, limit: int = 20, mode: str = "hybrid") -> dict:
    """检索语料库，返回带文件名 + 行号出处的片段。

    mode: hybrid（默认，BM25 + 语义向量 RRF 融合）/ keyword（仅 BM25）/
          semantic（仅向量，模型不可用自动降级）/ strict（旧 AND 行为）。
    """
    root_path = str(Path(root)) if root else str(corpus_dir())
    stamp = _corpus_stamp(Path(root_path))
    docs = load_corpus(root_path)
    results = rag.hybrid_search(
        query, docs, root=root_path, stamp=stamp, mode=mode, limit=limit
    )
    return {
        "query": query,
        "total": len(results),
        "scanned": len(docs),
        "mode": mode,
        "retrieval": rag.status(docs, stamp, root_path),
        "results": results,
    }
