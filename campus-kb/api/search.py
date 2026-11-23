"""语料库全文检索。

体量决定方案：corpus/text/ 目前 ~250KB、26 个文件，直接内存扫描即可精确命中，
不上 FTS5/向量库（中文分词是 FTS5 的坑，体量又用不上 BM25 的相关性排序收益）。
未来文件数量增长两个数量级再换 SQLite FTS5 trigram。
"""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

KB = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Doc:
    name: str  # 文件名（去扩展名），即语料条目 ID
    text: str


def corpus_dir() -> Path:
    override = os.environ.get("CAMPUS_CORPUS_DIR")
    return Path(override) if override else KB / "corpus" / "text"


def _corpus_stamp(root: Path) -> int:
    """语料目录版本戳：任一文件新增或改动都会变，用来让缓存失效。"""
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


def _clip(line: str, pos: int, width: int = 40) -> str:
    lo = max(0, pos - width)
    hi = min(len(line), pos + width)
    out = line[lo:hi].strip()
    return ("…" if lo > 0 else "") + out + ("…" if hi < len(line) else "")


def search(query: str, root: str | None = None, limit: int = 20) -> dict:
    """多关键词 AND 检索（空格分隔，不区分大小写）。

    返回按命中次数排序的行级结果，每行带文件名、行号与摘录，
    前端据此回链到具体文件。
    """
    docs = load_corpus(str(Path(root)) if root else str(corpus_dir()))
    terms = [t for t in query.split() if t]
    if not terms:
        return {"query": query, "total": 0, "scanned": len(docs), "results": []}

    lterms = [t.lower() for t in terms]
    results: list[dict] = []
    for doc in docs:
        low = doc.text.lower()
        if not all(t in low for t in lterms):
            continue
        doc_hits = 0
        lines_shown = 0
        for i, line in enumerate(doc.text.split("\n"), 1):
            ll = line.lower()
            if not all(t in ll for t in lterms):
                continue
            first = min(ll.find(t) for t in lterms)
            n = sum(ll.count(t) for t in lterms)
            doc_hits += n
            if lines_shown < 3:  # 每个文件最多展示 3 行，避免单文件刷屏
                results.append({
                    "file": doc.name,
                    "line": i,
                    "excerpt": _clip(line.strip(), first),
                    "hits": n,
                })
                lines_shown += 1
        if doc_hits:
            results.append({
                "file": doc.name,
                "line": 0,  # 0 = 文件级汇总行
                "excerpt": f"共命中 {doc_hits} 处",
                "hits": doc_hits,
            })

    results.sort(key=lambda r: -r["hits"])
    shown = [r for r in results if r["line"] != 0][:limit]
    return {
        "query": query,
        "total": len(results) - sum(1 for r in results if r["line"] == 0),
        "scanned": len(docs),
        "results": shown,
    }
