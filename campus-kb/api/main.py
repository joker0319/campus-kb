"""内容助手 API（RAG 知识库 + Agent）。

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

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

# checker.py 与 api/ 同级，保证 uvicorn 任意 cwd 启动都能导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import checker  # noqa: E402  # sys.path 调整必须在前
from . import agent  # noqa: E402
from . import deepseek  # noqa: E402
from .compose import compose_article, revise_article  # noqa: E402
from . import docx_io  # noqa: E402
from . import figures  # noqa: E402
from . import search as corpus_search  # noqa: E402

from .schemas import (  # noqa: E402
    AgentRequest,
    AgentResponse,
    ChatRequest,
    ChatResponse,
    ComposeRequest,
    ComposeResponse,
    Counts,
    Finding,
    ReviewFileResponse,
    ReviewRequest,
    ReviewResponse,
    ReviseRequest,
    ReviseResponse,
    RuleOut,
    RulesResponse,
)

app = FastAPI(
    title="内容助手 API",
    description="RAG 知识库 + Agent 助手 → 生成可溯源公众号文章；规范校验为其中一项功能",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    # allow_credentials=False 时可安全放行任意来源；这是无鉴权的内部校验工具，
    # 前端本地 dev 与 Vercel 静态站都要能调，故不枚举域名。
    allow_origins=["*"],
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


def to_findings(findings: list[dict]) -> tuple[list[Finding], Counts]:
    """引擎 finding → API Finding + 计数；稳定 key 的规则集中在一处。"""
    seen: Counter = Counter()
    out: list[Finding] = []
    for f in findings:
        seen[(f["rule_id"], f["line"])] += 1
        n = seen[(f["rule_id"], f["line"])]
        # 同规则同线多次命中（如一段里错多个词）追加 -2/-3
        key = f"{f['rule_id']}@{f['line']}" if n == 1 else f"{f['rule_id']}@{f['line']}-{n}"
        out.append(Finding(
            key=key,
            ruleId=f["rule_id"],
            severity=f["severity"],
            line=f["line"],
            message=f["message"],
            excerpt=f["excerpt"],
            suggestion=f.get("suggestion", ""),
            hit=f.get("hit", ""),
        ))
    sev = Counter(f["severity"] for f in findings)
    return out, Counts(
        total=len(findings),
        error=sev["error"],
        warn=sev["warn"],
        info=sev["info"],
    )


@app.post("/api/review")
def review(req: ReviewRequest, engine: EngineDep) -> ReviewResponse:
    rules, _skipped = engine
    findings = checker.run(req.content, rules, mode=req.mode)
    applied = sum(1 for r in rules if not r.get("context") or req.mode == "submission")
    out, counts = to_findings(findings)
    return ReviewResponse(findings=out, counts=counts, ruleCount=applied)


@app.get("/api/search")
def search(
    q: Annotated[str, Query(min_length=1, max_length=100, description="关键词或自然语言提问")],
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    mode: Annotated[
        str, Query(description="hybrid / keyword / semantic / strict")
    ] = "hybrid",
) -> dict:
    """语料库混合检索：BM25 + 本地语义向量 → 文件名 + 行号 + 摘录 + 召回方式。

    结果里的 retrieval 字段说明本次是否真的启用了语义路（模型缺失时自动降级 BM25）。
    """
    return corpus_search.search(q, limit=limit, mode=mode)


@app.post("/api/review-file")
async def review_file(engine: EngineDep, file: UploadFile = File(...)) -> ReviewFileResponse:
    """上传 docx → 提取纯文本 → 规则校验 → 返回命中与可下载的 Markdown 报告。

    只接受 .docx；损坏或空文档返回 400。规则与报告生成复用 checker.py，不重写。
    """
    filename = file.filename or "upload.docx"
    if not filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="仅支持 .docx 文件")
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件超过 20MB 限制")

    try:
        text = docx_io.extract_text(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    rules = engine[0]
    findings = checker.run(text, rules, mode="submission")
    applied = len(rules)  # submission 模式全量规则生效
    out, counts = to_findings(findings)
    report = docx_io.build_report(filename, findings, applied)
    return ReviewFileResponse(
        filename=filename,
        text=text,
        findings=out,
        counts=counts,
        ruleCount=applied,
        report=report,
    )


@app.post("/api/chat")
async def chat(req: ChatRequest, engine: EngineDep) -> ChatResponse:
    """AI 问答：检索知识库片段作为上下文，再交给 DeepSeek 解读。

    与确定性工具分开：本接口不产出校验结论，规则命中一律以 /api/review 为准。
    未配置密钥 503；上游调用失败 502。
    """
    try:
        result = await deepseek.ask(
            req.message,
            engine[0],
            [m.model_dump() for m in req.history],
        )
    except deepseek.DeepSeekNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except deepseek.DeepSeekUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ChatResponse(**result)


@app.post("/api/agent")
async def agent_chat(req: AgentRequest, engine: EngineDep) -> AgentResponse:
    """Agent 助手：模型自选工具，工具在后端确定性执行，结果回灌后生成回答。

    工具轨迹（steps）一并返回前端展示；校验类结论以规则引擎输出为准。
    未配置密钥 503；上游失败 502。
    """
    try:
        result = await agent.run_agent(
            req.message,
            engine[0],
            [m.model_dump() for m in req.history],
        )
    except deepseek.DeepSeekNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except deepseek.DeepSeekUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return AgentResponse(**result)


@app.post("/api/compose")
async def compose(req: ComposeRequest, engine: EngineDep) -> ComposeResponse:
    """文章生成：检索知识库 → DeepSeek 成稿 → 后端校验出处与规范。

    模型只用检索到的编号素材写稿；无出处的段落会被标记，不冒充有据。
    成稿另经规则引擎做发前检查（校验是项目的一个功能）。
    未配置密钥 503；上游失败 502。
    """
    try:
        result = await compose_article(req.topic, engine[0], style=req.style)
    except deepseek.DeepSeekNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except deepseek.DeepSeekUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ComposeResponse(**result)


@app.post("/api/compose/revise")
async def revise(req: ReviseRequest, engine: EngineDep) -> ReviseResponse:
    """改稿：在已有草稿上按指令继续改，沿用原素材编号，只重跑出处与规范检查。

    无状态设计——上一版 article 与 sources 由前端带回，服务端不缓存草稿。
    未配置密钥 503；上游失败 502。
    """
    try:
        result = await revise_article(
            req.topic,
            req.article,
            req.instruction,
            [s.model_dump() for s in req.sources],
            req.rules,
            engine[0],
            style=req.style,
        )
    except deepseek.DeepSeekNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except deepseek.DeepSeekUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ReviseResponse(**result)


@app.get("/api/figure/{figure_id}")
def get_figure(figure_id: str) -> FileResponse:
    """按 id 下发往期推文里的真实配图。

    语料图片目录不在 git 里（含真实师生影像），只在本机存在；索引缺失或图被删时
    返回 404，前端显示占位，不影响正文阅读。
    """
    path = figures.resolve(figure_id)
    if path is None:
        raise HTTPException(status_code=404, detail=f"配图不存在：{figure_id}")
    return FileResponse(path)


@app.get("/api/figures/stats")
def figure_stats() -> dict:
    """配图库概况：各类图张数，用于确认索引状态。"""
    if not figures.available():
        return {"total": 0, "kinds": {}, "hint": "先执行 uv run python tools/build_figure_index.py"}
    return {"total": figures.available(), "kinds": dict(figures.kind_stats())}
