"""校园投稿质量门 API。

只做薄封装：规则加载与校验逻辑全部复用 checker.py，
本文件不写任何校验规则。跨域放行 Vite 开发端口（5173）。

启动（在 campus-kb/ 下）：
  uv run uvicorn api.main:app --reload --port 8000
"""

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

# checker.py 与 api/ 同级，保证 uvicorn 任意 cwd 启动都能导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import checker  # noqa: E402  # sys.path 调整必须在前
from . import search as corpus_search  # noqa: E402

from .schemas import (  # noqa: E402
    Counts,
    Finding,
    ReviewRequest,
    ReviewResponse,
    RuleOut,
    RulesResponse,
)

app = FastAPI(
    title="campus-kb API",
    description="投稿质量门：19 条可溯源写作规范校验规则",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def get_engine() -> tuple[list[dict], list[str]]:
    """规则集启动后不变；FastAPI 依赖默认按调用缓存（lru_cache 语义）。"""
    return checker.load_rules()


EngineDep = Annotated[tuple[list[dict], list[str]], Depends(get_engine)]


def _source_by_id() -> dict[str, str]:
    """规则 id → 所属规范文件名与章节（rules/*.json 的顶层 source）。"""
    out: dict[str, str] = {}
    for p in sorted(checker.RULES_DIR.glob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        for r in data.get("rules", []):
            out[r["id"]] = data.get("source", p.stem)
    return out


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/rules")
def list_rules(engine: EngineDep) -> RulesResponse:
    rules, skipped = engine
    sources = _source_by_id()
    out = [
        RuleOut(
            id=r["id"],
            category=r["category"],
            severity=r["severity"],
            type=r["type"],
            desc=r["desc"],
            suggestion=r.get("suggestion", ""),
            source=sources.get(r["id"], ""),
            file=sources.get(r["id"], "").split("｜")[0],
        )
        for r in rules
    ]
    return RulesResponse(total=len(out), skipped=skipped, rules=out)


@app.post("/api/review")
def review(req: ReviewRequest, engine: EngineDep) -> ReviewResponse:
    rules, _skipped = engine
    findings = checker.run(req.content, rules, mode=req.mode)
    applied = sum(1 for r in rules if not r.get("context") or req.mode == "submission")

    # 稳定 key：ruleId@line；同规则同线多次命中（如一段里错多个词）追加 -2/-3
    seen: Counter = Counter()
    out: list[Finding] = []
    for f in findings:
        seen[(f["rule_id"], f["line"])] += 1
        n = seen[(f["rule_id"], f["line"])]
        key = f"{f['rule_id']}@{f['line']}" if n == 1 else f"{f['rule_id']}@{f['line']}-{n}"
        out.append(Finding(
            key=key,
            ruleId=f["rule_id"],
            severity=f["severity"],
            line=f["line"],
            message=f["message"],
            excerpt=f["excerpt"],
            suggestion=f.get("suggestion", ""),
        ))

    sev = Counter(f["severity"] for f in findings)
    return ReviewResponse(
        findings=out,
        counts=Counts(
            total=len(findings),
            error=sev["error"],
            warn=sev["warn"],
            info=sev["info"],
        ),
        ruleCount=applied,
    )


@app.get("/api/search")
def search(
    q: Annotated[str, Query(min_length=1, max_length=100, description="关键词，空格分隔为 AND")],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> dict:
    """语料库全文检索：关键词 → 文件名 + 行号 + 摘录。"""
    return corpus_search.search(q, limit=limit)
