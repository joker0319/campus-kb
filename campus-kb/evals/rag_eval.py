"""RAG 检索评测：用真实提问锁住召回基线。

设计取舍：
- 期望写成「文件名 + 必须出现的关键词」，而不是写死行号。语料新增或重切块后
  行号会变，关键词不会；只要正确段落还在 top-k 就算命中。
- 同时记录 hit@k、MRR 与是否降级。改 prompt / 改分块 / 换 embedding 前后跑同一份
  用例，能直接看出是变好还是变差。
- 校验阶段会确认每条期望都能在语料里找到，避免评测集自己先腐烂。

用法：
    CAMPUS_EMBEDDING=off python -m evals.rag_eval --mode keyword
    python -m evals.rag_eval --mode hybrid --report /tmp/rag_baseline.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from api import rag
from api.search import corpus_dir, load_corpus, search

CASES_PATH = Path(__file__).with_name("rag_cases.json")


def load_cases(path: str | Path | None = None) -> list[dict[str, Any]]:
    """读取评测集；缺字段时直接报错，避免静默漏评。"""
    source = Path(path) if path else CASES_PATH
    data = json.loads(source.read_text(encoding="utf-8"))
    cases = data.get("cases") or []
    if not cases:
        raise ValueError(f"评测集为空：{source}")
    for case in cases:
        if not case.get("id") or not case.get("query") or not case.get("expect"):
            raise ValueError(f"用例缺 id/query/expect：{case}")
        for exp in case["expect"]:
            if not exp.get("file") or not exp.get("contains"):
                raise ValueError(f"期望缺 file/contains：{case['id']} {exp}")
    return cases


def validate_cases(cases: list[dict[str, Any]], root: str | None = None) -> None:
    """确认每个期望关键词确实存在于对应语料文件，防止评测集过期。"""
    docs = load_corpus(root or str(corpus_dir()))
    texts: dict[str, list[str]] = {}
    for chunk in rag.build_chunks(docs):
        texts.setdefault(chunk.file, []).append(chunk.text)
    missing: list[str] = []
    for case in cases:
        for exp in case["expect"]:
            if not any(exp["contains"] in t for t in texts.get(exp["file"], [])):
                missing.append(f"{case['id']}: {exp['file']} / {exp['contains']}")
    if missing:
        raise ValueError("评测集期望与语料不匹配：\n" + "\n".join(missing))


def evaluate(
    cases: list[dict[str, Any]],
    *,
    mode: str = "hybrid",
    k: int = 5,
    root: str | None = None,
) -> dict[str, Any]:
    """逐条检索并打分。命中 = top-k 内出现期望文件且片段含关键词。"""
    rows: list[dict[str, Any]] = []
    retrieval: dict[str, Any] = {}
    hits = 0
    reciprocal = 0.0

    for case in cases:
        result = search(case["query"], root=root, limit=k, mode=mode)
        if not retrieval:
            retrieval = result.get("retrieval") or {}
        rank: int | None = None
        for position, item in enumerate(result["results"], 1):
            text = item.get("text") or item.get("excerpt") or ""
            if any(
                item.get("file") == exp["file"] and exp["contains"] in text
                for exp in case["expect"]
            ):
                rank = position
                break
        if rank:
            hits += 1
            reciprocal += 1.0 / rank
        top = result["results"][0]["file"] if result["results"] else ""
        rows.append({
            "id": case["id"],
            "query": case["query"],
            "status": "PASS" if rank else "FAIL",
            "rank": rank,
            "top1": top,
        })

    summary = {
        "mode": mode,
        "k": k,
        "cases": len(cases),
        "hits": hits,
        "hit_at_k": round(hits / max(1, len(cases)), 4),
        "mrr": round(reciprocal / max(1, len(cases)), 4),
        "degraded": bool(retrieval.get("degraded", True)),
        "retrieval": retrieval,
    }
    return {"summary": summary, "rows": rows}


def format_report(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        f"模式={s['mode']}  k={s['k']}  用例={s['cases']}",
        f"hit@{s['k']}={s['hit_at_k']:.1%} ({s['hits']}/{s['cases']})  "
        f"MRR={s['mrr']:.4f}  降级={'是' if s['degraded'] else '否'}",
        "",
    ]
    for row in report["rows"]:
        rank = str(row["rank"]) if row["rank"] else "-"
        lines.append(
            f"{row['status']:4s} rank={rank:>2s}  {row['id']:<22s} "
            f"top1={row['top1'][:42]}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RAG 检索评测")
    parser.add_argument("--mode", default="hybrid", choices=["hybrid", "keyword", "semantic"])
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--cases", help="自定义评测集 JSON")
    parser.add_argument("--corpus-dir", help="自定义语料目录")
    parser.add_argument("--report", help="把完整结果写成 JSON")
    parser.add_argument("--fail-under", type=float, help="hit@k 低于此值时退出码为 1")
    args = parser.parse_args(argv)

    cases = load_cases(args.cases)
    validate_cases(cases, args.corpus_dir)
    report = evaluate(cases, mode=args.mode, k=args.k, root=args.corpus_dir)
    print(format_report(report))

    if args.report:
        Path(args.report).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    if args.fail_under is not None and report["summary"]["hit_at_k"] < args.fail_under:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
