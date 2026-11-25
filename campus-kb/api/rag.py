"""RAG 语义检索：段落分块 + 本地 embedding + BM25 混合召回。

为什么这样设计：
  1. 事实与出处始终由后端确定性约束——每个 chunk 都带 file / start_line / end_line，
     语义向量只是「怎么找到相关段落」，不改变「答案必须能回链到原文」这条红线。
  2. 稀疏路（BM25，中文字符 2-gram）保证词面精确命中与可解释的相关性排序；
     稠密路（本地 ONNX embedding）补语义召回：换词、近义、口语化提问也能命中。
  3. 两路用 RRF（Reciprocal Rank Fusion）按名次融合，绕开 BM25 分与余弦分不同量纲的问题。
  4. embedding 模型缺失 / 下载失败 / 被显式关闭时自动降级为纯 BM25，功能永不挂。
  5. 向量索引按语料目录版本戳落盘缓存；语料一变自动重建，无需重启进程。

模型使用本地 ONNX（fastembed + BAAI/bge-small-zh-v1.5），不调用任何外部 embedding API，
不需要额外密钥；首次使用需下载一次模型（约 90MB，走 HF_ENDPOINT 镜像，默认 hf-mirror.com）。
"""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Sequence

CHUNK_VERSION = 2        # 分块算法版本；改动分块逻辑时 +1，旧索引自动失效
CHUNK_CHARS = 360        # 目标块大小（字符）
CHUNK_OVERLAP = 60       # 超长单行切分时的重叠
MIN_CHUNK_CHARS = 30     # 短于此的碎片并入相邻块
BM25_K1 = 1.5
BM25_B = 0.75
RRF_K = 60
CANDIDATE_K = 40         # 每路进融合的候选数

def _load_local_env() -> None:
    """把 campus-kb/.env 里的 CAMPUS_* / HF_* 配置补进 os.environ（shell 变量优先）。

    deepseek.Settings 由 pydantic-settings 读 .env，但本模块直接用 os.environ；
    这里做一次轻量补齐，让检索侧配置也走同一个 .env，不必另记一套启动环境变量。
    """
    path = Path(__file__).resolve().parent.parent / ".env"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key.startswith(("CAMPUS_", "HF_")) and key not in os.environ:
            os.environ[key] = val


_load_local_env()

MODEL_NAME = os.environ.get("CAMPUS_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
DEFAULT_HF_ENDPOINT = "https://hf-mirror.com"

_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+|[\u4e00-\u9fff]+")


@dataclass(frozen=True)
class Chunk:
    file: str
    start_line: int
    end_line: int
    text: str


def embedding_enabled() -> bool:
    """是否允许尝试稠密检索。off = 强制纯 BM25（测试与离线环境用）。"""
    return os.environ.get("CAMPUS_EMBEDDING", "auto").lower() not in {"0", "off", "false", "no"}


def tokenize(text: str) -> list[str]:
    """中文按 2-gram、英文数字按词。与 deepseek._terms 同思路，但不限数量。"""
    out: list[str] = []
    for part in _TOKEN_RE.findall(text.lower()):
        if part[0].isascii():
            if len(part) >= 2:
                out.append(part)
        elif len(part) == 1:
            out.append(part)
        else:
            out.extend(part[i : i + 2] for i in range(len(part) - 1))
    return out


def _flush(out: list[Chunk], name: str, buf: list[tuple[int, str]]) -> None:
    if not buf:
        return
    text = "\n".join(s for _, s in buf).strip()
    # 短文件（语料里最短只有 14 字）不能被最小长度过滤掉，否则整份档案检索不到。
    # MIN_CHUNK_CHARS 只用于过滤「超长单行」切分产生的尾部碎片。
    if text:
        out.append(Chunk(name, buf[0][0], buf[-1][0], text))


def build_chunks(docs: Iterable) -> tuple[Chunk, ...]:
    """按行聚合分块，保留起止行号；空行是弱边界，超长行按字符滑窗切。

    只保留非空行，所以 start_line/end_line 覆盖的是「这一段实际取自哪几行」，
    回链到原文件时按这两个行号取区间即可，不会错位。
    """
    out: list[Chunk] = []
    for doc in docs:
        buf: list[tuple[int, str]] = []
        cur = 0
        for i, raw in enumerate(doc.text.split("\n"), 1):
            s = raw.strip()
            if not s:
                # 空行分段：攒够大半块就切，避免把两个主题硬拼进同一向量
                if cur >= CHUNK_CHARS * 0.6:
                    _flush(out, doc.name, buf)
                    buf, cur = [], 0
                continue
            if len(s) > CHUNK_CHARS:
                _flush(out, doc.name, buf)
                buf, cur = [], 0
                step = CHUNK_CHARS - CHUNK_OVERLAP
                for j in range(0, len(s), step):
                    part = s[j : j + CHUNK_CHARS]
                    if len(part) >= MIN_CHUNK_CHARS:
                        out.append(Chunk(doc.name, i, i, part))
                continue
            if cur + len(s) > CHUNK_CHARS:
                _flush(out, doc.name, buf)
                # 行级重叠：把上一块最后一行带进下一块，缓解语义被切断
                tail = buf[-1]
                buf, cur = [tail], len(tail[1])
            buf.append((i, s))
            cur += len(s)
        _flush(out, doc.name, buf)
    return tuple(out)


class BM25Index:
    """纯 Python BM25，避免引入额外依赖；语料规模 <1000 块，内存里算足够快。"""

    def __init__(self, chunks: Sequence[Chunk]) -> None:
        self.chunks = chunks
        self.doc_tokens = [tokenize(c.text) for c in chunks]
        self.doc_len = [len(t) for t in self.doc_tokens]
        self.avgdl = sum(self.doc_len) / max(1, len(self.doc_len))
        self.postings: dict[str, list[tuple[int, int]]] = {}
        self.df: dict[str, int] = {}
        for idx, toks in enumerate(self.doc_tokens):
            counts: dict[str, int] = {}
            for t in toks:
                counts[t] = counts.get(t, 0) + 1
            for t, c in counts.items():
                self.df[t] = self.df.get(t, 0) + 1
                self.postings.setdefault(t, []).append((idx, c))

    def rank(self, query: str) -> list[tuple[int, float]]:
        qtoks = set(tokenize(query))
        n = len(self.chunks)
        scores: dict[int, float] = {}
        for t in qtoks:
            pl = self.postings.get(t)
            if not pl:
                continue
            idf = math.log(1 + (n - self.df[t] + 0.5) / (self.df[t] + 0.5))
            for idx, tf in pl:
                dl = self.doc_len[idx]
                denom = tf + BM25_K1 * (1 - BM25_B + BM25_B * dl / self.avgdl)
                scores[idx] = scores.get(idx, 0.0) + idf * tf * (BM25_K1 + 1) / denom
        return sorted(scores.items(), key=lambda x: -x[1])


_model: object | None = None
_model_failed = False


def _get_model():
    """惰性加载 ONNX 模型；任何失败都记下并永久降级（避免每请求重试拖垮接口）。"""
    global _model, _model_failed
    if not embedding_enabled() or _model_failed:
        return None
    if _model is None:
        try:
            # 镜像可配；用户机器能直连 HF 时可用 CAMPUS_HF_ENDPOINT 覆盖
            os.environ.setdefault(
                "HF_ENDPOINT", os.environ.get("CAMPUS_HF_ENDPOINT", DEFAULT_HF_ENDPOINT)
            )
            from fastembed import TextEmbedding

            _model = TextEmbedding(model_name=MODEL_NAME)
        except Exception:  # 模型缺失、下载失败、onnxruntime 不可用……
            _model_failed = True
            _model = None
    return _model


def _index_dir(root: str) -> Path:
    override = os.environ.get("CAMPUS_INDEX_DIR")
    return Path(override) if override else Path(root).parent / ".index"


@lru_cache(maxsize=4)
def _chunks_for(docs: tuple, stamp: int) -> tuple[Chunk, ...]:
    return build_chunks(docs)


@lru_cache(maxsize=4)
def _bm25_for(chunks: tuple[Chunk, ...]) -> BM25Index:
    return BM25Index(chunks)


@lru_cache(maxsize=2)
def _vectors_for(chunks: tuple[Chunk, ...], stamp: int, root: str):
    """返回 (vectors, dense_available)。命中落盘索引时不再重算 chunk 向量。"""
    path = _index_dir(root) / f"vectors-{MODEL_NAME.replace('/', '_')}-v{CHUNK_VERSION}-{stamp}.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if (
                data.get("model") == MODEL_NAME
                and data.get("stamp") == stamp
                and len(data.get("vectors", [])) == len(chunks)
            ):
                return data["vectors"], True
        except (OSError, ValueError):
            pass

    model = _get_model()
    if model is None:
        return None, False
    try:
        vecs = [[float(x) for x in v] for v in model.embed([c.text for c in chunks])]
    except Exception:
        return None, False
    if len(vecs) != len(chunks):
        return None, False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "model": MODEL_NAME,
                    "stamp": stamp,
                    "chunks": len(chunks),
                    "vectors": [[round(x, 5) for x in v] for v in vecs],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except OSError:
        pass  # 索引写不了不影响本次检索
    return vecs, True


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _query_vector(model, query: str):
    """bge 系列对查询有专门前缀，fastembed 的 query_embed 会处理。"""
    try:
        return [float(x) for x in next(iter(model.query_embed([query])))]
    except Exception:
        return [float(x) for x in next(iter(model.embed([query])))]


def dense_rank(
    query: str, chunks: tuple[Chunk, ...], stamp: int, root: str, k: int
) -> list[tuple[int, float]]:
    vecs, ok = _vectors_for(chunks, stamp, root)
    if not ok or vecs is None:
        return []
    model = _get_model()
    if model is None:
        return []
    try:
        qv = _query_vector(model, query)
    except Exception:
        return []
    scored = [(i, _cosine(qv, v)) for i, v in enumerate(vecs)]
    return sorted(scored, key=lambda x: -x[1])[:k]


def _rrf(rankings: Sequence[Sequence[tuple[int, float]]]) -> list[tuple[int, float, int]]:
    """按名次融合；返回 (chunk_idx, rrf_score, 命中路数位掩码)。"""
    scores: dict[int, float] = {}
    mask: dict[int, int] = {}
    for bit, ranking in enumerate(rankings):
        for rank, (idx, _) in enumerate(ranking, 1):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (RRF_K + rank)
            mask[idx] = mask.get(idx, 0) | (1 << bit)
    return [(i, s, mask[i]) for i, s in sorted(scores.items(), key=lambda x: -x[1])]


def _excerpt(chunk: Chunk, query: str, width: int = 96) -> str:
    text = " ".join(chunk.text.split())
    low = text.lower()
    positions = [low.find(t) for t in tokenize(query) if t]
    pos = min((p for p in positions if p >= 0), default=-1)
    if pos < 0:
        return text[:width] + ("…" if len(text) > width else "")
    lo = max(0, pos - 28)
    hi = min(len(text), pos + width - 28)
    return ("…" if lo > 0 else "") + text[lo:hi].strip() + ("…" if hi < len(text) else "")


def hybrid_search(
    query: str,
    docs: tuple,
    *,
    root: str,
    stamp: int,
    mode: str = "hybrid",
    limit: int = 20,
) -> list[dict]:
    """混合召回主入口。

    mode:
      hybrid  —— BM25 + 稠密向量，RRF 融合（默认）
      keyword —— 仅 BM25（比旧的「全部词 AND」召回更全、带相关性排序）
      semantic—— 仅稠密向量；模型不可用时自动回落 keyword
      strict  —— 旧的逐行 AND 行为，留给回归对照 / 回滚
    """
    if not query.strip():
        return []
    if mode == "strict":
        return _strict_search(query, docs, limit)
    if mode not in {"hybrid", "keyword", "semantic"}:
        mode = "hybrid"

    chunks = _chunks_for(docs, stamp)
    if not chunks:
        return []

    sparse = _bm25_for(chunks).rank(query)[:CANDIDATE_K] if mode != "semantic" else []
    dense = dense_rank(query, chunks, stamp, root, CANDIDATE_K) if mode != "keyword" else []
    if not sparse and not dense and mode == "semantic":
        # 稠密路不可用（模型未下载/被禁用）——诚实降级，不假装做过语义检索
        sparse = _bm25_for(chunks).rank(query)[:CANDIDATE_K]
        mode = "keyword"

    fused = _rrf([sparse, dense])
    sparse_scores = dict(sparse)
    dense_scores = dict(dense)
    out: list[dict] = []
    for idx, score, mask in fused[:limit]:
        c = chunks[idx]
        via = "hybrid" if mask == 0b11 else ("semantic" if mask == 0b10 else "keyword")
        out.append(
            {
                "file": c.file,
                "line": c.start_line,
                "endLine": c.end_line,
                "excerpt": _excerpt(c, query),
                # 完整块给成稿链路用：96 字摘要只服务检索结果列表，不能当写作素材。
                # 摘要按首个查询词居中截取，关键事实（如「位列第52位」）常被截在窗口外，
                # 模型拿不到就只能写「（素材不足，待补充）」。
                "text": c.text,
                "hits": round(sparse_scores.get(idx, 0.0) * 10) + 1,
                "score": round(score, 6),
                "similarity": round(dense_scores.get(idx, 0.0), 4),
                "matchedBy": via,
            }
        )
    return out


def _strict_search(query: str, docs: tuple, limit: int) -> list[dict]:
    """旧行为：多词 AND、行级命中、按命中次数排序。保留作对照。"""
    terms = [t.lower() for t in query.split() if t]
    if not terms:
        return []
    rows: list[dict] = []
    for doc in docs:
        lines_shown = 0
        for i, line in enumerate(doc.text.split("\n"), 1):
            ll = line.lower()
            if not all(t in ll for t in terms):
                continue
            first = min(ll.find(t) for t in terms)
            n = sum(ll.count(t) for t in terms)
            if lines_shown < 3:
                s = line.strip()
                rows.append(
                    {
                        "file": doc.name,
                        "line": i,
                        "endLine": i,
                        "excerpt": s[max(0, first - 40) : first + 40].strip(),
                        "text": s,
                        "hits": n,
                        "score": 0.0,
                        "similarity": 0.0,
                        "matchedBy": "strict",
                    }
                )
                lines_shown += 1
    rows.sort(key=lambda r: -r["hits"])
    return rows[:limit]


def status(docs: tuple, stamp: int, root: str) -> dict:
    """轻量状态查询：只看索引文件在不在，不触发模型加载或全量编码。

    /api/search 每次都会带上这份状态，所以这里绝不能做重活。
    """
    chunks = _chunks_for(docs, stamp)
    path = _index_dir(root) / f"vectors-{MODEL_NAME.replace('/', '_')}-v{CHUNK_VERSION}-{stamp}.json"
    dense = bool(chunks) and path.exists() and not _model_failed and embedding_enabled()
    return {
        "mode": "hybrid" if dense else "keyword",
        "chunks": len(chunks),
        "model": MODEL_NAME if dense else None,
        "dense": dense,
        "degraded": not dense,
        "indexDir": str(_index_dir(root)),
    }


def clear_caches() -> None:
    """测试用：清空索引与模型状态，重新走一遍加载/降级路径。"""
    global _model, _model_failed
    _chunks_for.cache_clear()
    _bm25_for.cache_clear()
    _vectors_for.cache_clear()
    _model = None
    _model_failed = False
