"""Agent 助手：DeepSeek Function Calling + 本地确定性工具。

与 deepseek.py（单轮 RAG 问答）的区别：
  这里模型自己决定调用哪个工具、传什么参数；工具在本机执行（规则/档案/校验），
  结果作为 tool 消息回灌，模型基于真实结果组织回答。模型不产出校验结论。

工具全部是确定性函数：
  - search_rules    规则库关键词检索
  - search_archive  档案库全文检索
  - review_draft    调用 checker.py 规则引擎校验（结论以此为准）

循环上限 MAX_STEPS，防止模型反复调用不收敛。
配置与密钥复用 deepseek.Settings（DEEPSEEK_API_KEY）。
"""

from __future__ import annotations

import json
from typing import Any, AsyncIterator, Callable

import httpx

import checker

from . import deepseek, search as corpus_search

MAX_STEPS = 4  # 工具调用轮数上限（每轮 = 一次模型请求）

SYSTEM_PROMPT = """你是香港城市大学（东莞）媒体传讯处的内容助手，服务于「RAG 知识库 + Agent → 生成可用微信公众号文章」这一主线。
你的目标是帮用户基于知识库（规范、档案、往期推文）写出能直接使用的公众号文章内容；当前通过调用工具检索有出处的素材与规范来支撑写作与问答。
你可以调用工具查询知识库，再基于工具返回的真实结果回答用户。

铁律：
- 涉及「某条规范/标点/校名/写法是否正确」→ 必须调用 search_rules，不要凭记忆回答。
- 涉及「档案里记载了什么/某活动或人物的历史资料」→ 必须调用 search_archive。
- 涉及「帮我检查这段稿件/这段正文有没有问题」→ 必须调用 review_draft；校验结论只能复述工具返回的命中，不得自行增减或改写严重程度。
- 只有工具结果里有的事实才能说；工具没查到就明确说知识库中没有依据，不要编造。
- 一次可以调用多个工具；信息足够后直接用中文回答，不要重复调用。
- 回答简洁，引用档案时带上工具结果里的文件名与行号。
"""

# 权威口径取自单一事实源 authority.json，避免在多处硬编码后再次漂移
_AUTHORITY = checker.authority_brief()
if _AUTHORITY:
    SYSTEM_PROMPT += (
        "\n【权威口径】" + _AUTHORITY
        + "\n涉及上述口径时一律按权威值作答，不得引用被忽略的旧版或副本数值。"
    )

# 工具定义（OpenAI / DeepSeek function calling 格式）
TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_rules",
            "description": "查询写作规范与规则。当用户问某条规范怎么写、标点/校名/序数/标题是否正确、有哪些规则时调用。参数 keyword 为检索关键词或短语。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "检索关键词，如「标点」「校名」「序数」"},
                },
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_archive",
            "description": (
                "在入库的历史档案与往期推文中混合检索（词面 BM25 + 本地语义向量）。"
                "支持直接用自然语言提问，换一种说法也能找到语义相关的段落；"
                "不必刻意拆解或堆砌关键词。结果带文件名、行号与摘录，引用时请带上出处。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "检索词或自然语言提问，如「奠基」「学生心理咨询在哪里预约」"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "review_draft",
            "description": "校验一段稿件正文是否符合写作规范。当用户粘贴文本要求检查、校对、指出问题时调用。返回确定性规则引擎的命中结果与改法。",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "待校验的稿件正文"},
                },
                "required": ["content"],
            },
        },
    },
]

# 工具执行结果的结构：给模型看的是 text，给前端看的是 structured
ToolResult = dict[str, Any]


def _exec_search_rules(args: dict[str, Any], rules: list[dict]) -> ToolResult:
    keyword = str(args.get("keyword", "")).strip()
    if not keyword:
        return {"text": "关键词为空，未查询到规则。", "structured": {"kind": "rules", "items": [], "keyword": keyword}}

    terms = deepseek._terms(keyword)
    scored = []
    for rule in rules:
        hay = " ".join(str(rule.get(k, "")) for k in ("id", "category", "desc", "suggestion", "type"))
        hit = deepseek._score(hay, terms)
        if hit:
            scored.append((hit, rule))
    scored.sort(key=lambda x: -x[0])

    items = []
    lines = []
    for hit, rule in scored[:8]:
        detail = f"[{rule['id']}] {rule['desc']}"
        if rule.get("suggestion"):
            detail += f"；建议：{rule['suggestion']}"
        source = rule.get("source", "")
        items.append({
            "id": rule["id"], "title": rule["id"],
            "desc": rule["desc"], "suggestion": rule.get("suggestion", ""),
            "source": source, "category": rule.get("category", ""),
        })
        lines.append(f"- {detail}" + (f"（出处：{source}）" if source else ""))

    if not lines:
        return {
            "text": f"规则库中未找到与「{keyword}」相关的规则。",
            "structured": {"kind": "rules", "items": [], "keyword": keyword},
        }
    return {
        "text": f"规则库命中 {len(scored)} 条，列出前 {len(lines)} 条：\n" + "\n".join(lines),
        "structured": {"kind": "rules", "items": items, "keyword": keyword, "total": len(scored)},
    }


CONTEXT_SPAN = 2      # 命中行前后各带几行原文
CONTEXT_MAX_ROWS = 5  # 只给前几条加上下文，控制 token


def _context_for(name: str, line_no: int) -> str:
    """取命中行附近的原始段落。

    关键词检索只命中含检索词的行，但关键信息往往分散在相邻行：问「在哪预约」，
    命中「预约方式」那行，地点和时间却写在隔壁。只把单行交给模型，它会回答
    「档案中没有记载」——不是没记载，是没给它看。
    """
    try:
        docs = corpus_search.load_corpus(str(corpus_search.corpus_dir()))
    except OSError:
        return ""
    doc = next((d for d in docs if d.name == name), None)
    if doc is None:
        return ""
    lines = doc.text.split("\n")
    lo = max(0, line_no - 1 - CONTEXT_SPAN)
    hi = min(len(lines), line_no + CONTEXT_SPAN)
    parts = [line.strip() for line in lines[lo:hi] if line.strip()]
    return " / ".join(parts)


def _exec_search_archive(args: dict[str, Any]) -> ToolResult:
    query = str(args.get("query", "")).strip()
    if not query:
        return {"text": "检索词为空，未查询到档案。", "structured": {"kind": "archive", "items": [], "query": query}}

    try:
        result = corpus_search.search(query, limit=8)
    except OSError:
        result = {"total": 0, "scanned": 0, "results": []}

    # 多词 AND 极容易空手而归：模型习惯把「情绪 求助 心理」一起塞进来，
    # 而三个词几乎不会同时出现在同一行。空结果时退化成单关键词重试，
    # 否则模型会误判「档案里没记载」——其实只是查法太严。
    retried_with = ""
    if not result.get("results"):
        terms = sorted({t for t in query.split() if len(t) >= 2}, key=len, reverse=True)
        for term in terms[:3]:
            alt = corpus_search.search(term, limit=8)
            if alt.get("results"):
                result = alt
                retried_with = term
                break

    rows = result.get("results", [])
    items = [
        {"file": r["file"], "line": r["line"], "excerpt": r["excerpt"], "hits": r["hits"]}
        for r in rows
    ]
    if not rows:
        return {
            "text": f"档案库中未检索到与「{query}」相关的记录（扫描 {result.get('scanned', 0)} 份档案）。",
            "structured": {"kind": "archive", "items": [], "query": query, "scanned": result.get("scanned", 0)},
        }

    lines: list[str] = []
    for idx, r in enumerate(rows):
        entry = f"- {r['file']} 第 {r['line']} 行：{r['excerpt']}"
        if idx < CONTEXT_MAX_ROWS:
            context = _context_for(r["file"], r["line"])
            if context:
                entry += f"\n  该处上下文：{context}"
        lines.append(entry)

    header = f"档案命中 {result.get('total', 0)} 处（扫描 {result.get('scanned', 0)} 份）"
    if retried_with:
        header = (
            f"「{query}」要求多个词同行，命中太少，已改用「{retried_with}」检索。{header}"
        )

    return {
        "text": header + "：\n" + "\n".join(lines),
        "structured": {
            "kind": "archive", "items": items, "query": query,
            "total": result.get("total", 0), "scanned": result.get("scanned", 0),
            "retriedWith": retried_with,
        },
    }


def _exec_review_draft(args: dict[str, Any], rules: list[dict]) -> ToolResult:
    content = str(args.get("content", "")).strip()
    if not content:
        return {
            "text": "正文为空，无法校验。",
            "structured": {"kind": "review", "items": [], "counts": {"total": 0, "error": 0, "warn": 0, "info": 0}},
        }

    findings = checker.run(content, rules, mode="submission")
    sev = {"error": 0, "warn": 0, "info": 0}
    for f in findings:
        sev[f["severity"]] = sev.get(f["severity"], 0) + 1

    items = [
        {
            "ruleId": f["rule_id"], "line": f["line"], "severity": f["severity"],
            "message": f["message"], "suggestion": f.get("suggestion", ""),
            "hit": f.get("hit", ""), "excerpt": f.get("excerpt", ""),
        }
        for f in findings
    ]
    if not findings:
        return {
            "text": f"规则引擎校验完成：全文 {len(content)} 字，19 条规则全部通过，未发现问题。",
            "structured": {"kind": "review", "items": [], "counts": {"total": 0, **sev}},
        }

    lines = []
    for f in findings[:20]:
        lines.append(
            f"- [{f['rule_id']}] 第 {f['line']} 行 · {f['severity']}：{f['message']}"
            + (f" → 建议：{f['suggestion']}" if f.get("suggestion") else "")
        )
    more = f"\n（另有 {len(findings) - 20} 条未列出）" if len(findings) > 20 else ""
    return {
        "text": (
            f"规则引擎校验完成：发现 {len(findings)} 个问题"
            f"（错误 {sev['error']} / 警告 {sev['warn']} / 提示 {sev['info']}）。\n"
            + "\n".join(lines) + more
        ),
        "structured": {"kind": "review", "items": items, "counts": {"total": len(findings), **sev}},
    }


def make_executor(rules: list[dict]) -> Callable[[str, dict[str, Any]], ToolResult]:
    """返回一个把工具名与参数映射到本地执行结果的函数（便于测试注入）。"""

    def execute(name: str, args: dict[str, Any]) -> ToolResult:
        if name == "search_rules":
            return _exec_search_rules(args, rules)
        if name == "search_archive":
            return _exec_search_archive(args)
        if name == "review_draft":
            return _exec_review_draft(args, rules)
        return {"text": f"未知工具：{name}", "structured": {"kind": "error", "name": name}}

    return execute


def _parse_args(raw: Any) -> dict[str, Any]:
    """模型可能返回非法 JSON，解析失败时降级为空参数，由工具给出空值提示。"""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
            return value if isinstance(value, dict) else {}
        except (ValueError, TypeError):
            return {}
    return {}


def _build_messages(question: str, history: list[dict] | None) -> list[dict[str, Any]]:
    """流式与非流式共用同一段上下文拼装，避免两条路径的对话历史漂移。"""
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in (history or [])[-6:]:
        role = turn.get("role")
        if role in ("user", "assistant") and isinstance(turn.get("content"), str):
            messages.append({"role": role, "content": turn["content"]})
    messages.append({"role": "user", "content": question})
    return messages


async def run_agent(
    question: str,
    rules: list[dict],
    history: list[dict] | None = None,
    settings: deepseek.Settings | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict:
    """执行 Agent 循环：模型选工具 → 本地执行 → 回灌 → 最终回答。

    返回 { answer, steps, model, usedTools }；steps 为工具调用轨迹，供前端展示。
    """
    cfg = settings or deepseek.get_settings()
    if not cfg.configured:
        raise deepseek.DeepSeekNotConfigured("未配置 DEEPSEEK_API_KEY，请在 campus-kb/.env 中填入密钥")

    execute = make_executor(rules)
    messages = _build_messages(question, history)

    url = f"{cfg.deepseek_base_url.rstrip('/')}/chat/completions"
    steps: list[dict[str, Any]] = []
    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=90)

    try:
        for _step in range(MAX_STEPS):
            response = await http.post(
                url,
                headers={
                    "Authorization": f"Bearer {cfg.deepseek_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": cfg.deepseek_model,
                    "messages": messages,
                    "tools": TOOLS,
                    "tool_choice": "auto",
                    "temperature": 0.1,
                    "stream": False,
                },
            )
            response.raise_for_status()
            data = response.json()
            message = data["choices"][0]["message"]
            tool_calls = message.get("tool_calls") or []

            if not tool_calls:
                answer = (message.get("content") or "").strip()
                return {
                    "answer": answer,
                    "steps": steps,
                    "model": cfg.deepseek_model,
                    "usedTools": [s["tool"] for s in steps],
                }

            # 把 assistant 的 tool_calls 原样加入历史，再逐条回灌 tool 结果
            messages.append({
                "role": "assistant",
                "content": message.get("content") or "",
                "tool_calls": tool_calls,
            })
            for call in tool_calls:
                fn = call.get("function") or {}
                name = fn.get("name", "")
                args = _parse_args(fn.get("arguments"))
                result = execute(name, args)
                steps.append({
                    "tool": name, "args": args,
                    "result": result["structured"],
                    "callId": call.get("id", ""),
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "content": result["text"],
                })

        # 达到步数上限仍未收敛：用最后一次工具结果明确收尾，不假装正常回答
        return {
            "answer": "已查询知识库，但问题较复杂，工具调用达到上限。请缩小问题范围后重试，或直接查看下方工具返回的结果。",
            "steps": steps,
            "model": cfg.deepseek_model,
            "usedTools": [s["tool"] for s in steps],
            "truncated": True,
        }
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise deepseek.DeepSeekUnavailable(f"DeepSeek Agent 调用失败：{exc}") from exc
    finally:
        if owns_client:
            await http.aclose()


def _accumulate_tool_calls(buf: dict[int, dict[str, Any]], parts: list[dict]) -> None:
    """把流式分片合并成完整的 tool_calls。

    OpenAI/DeepSeek 的流式 function calling 里 name 与 arguments 会跨多帧到达，
    用 index 归组后逐段拼接；直接取最后一帧只会拿到残缺的 JSON 参数。
    """
    for part in parts:
        idx = int(part.get("index") or 0)
        cur = buf.setdefault(
            idx,
            {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
        )
        if part.get("id"):
            cur["id"] = str(part["id"])
        if part.get("type"):
            cur["type"] = str(part["type"])
        fn = part.get("function") or {}
        if fn.get("name"):
            cur["function"]["name"] += str(fn["name"])
        if fn.get("arguments"):
            cur["function"]["arguments"] += str(fn["arguments"])


async def run_agent_stream(
    question: str,
    rules: list[dict],
    history: list[dict] | None = None,
    settings: deepseek.Settings | None = None,
    client: httpx.AsyncClient | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Agent 循环的流式版本，产出 SSE 事件字典。

    事件序列：`meta`（模型名）→ 每完成一次工具调用一条 `step` → 最终回答的若干
    `delta` → `done`（完整结果，字段同 AgentResponse）。工具决策轮仍走流式请求，
    但没有 tool_calls 时才会有 content，因此逐段推给前端不会与工具轨迹串台。

    与 run_agent 并存：非流式端点保持原行为，避免改动既有调用方与测试。
    """
    cfg = settings or deepseek.get_settings()
    if not cfg.configured:
        raise deepseek.DeepSeekNotConfigured("未配置 DEEPSEEK_API_KEY，请在 campus-kb/.env 中填入密钥")

    execute = make_executor(rules)
    messages = _build_messages(question, history)
    url = f"{cfg.deepseek_base_url.rstrip('/')}/chat/completions"
    steps: list[dict[str, Any]] = []
    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=90)

    try:
        yield {"type": "meta", "model": cfg.deepseek_model}
        for _step in range(MAX_STEPS):
            answer_parts: list[str] = []
            calls: dict[int, dict[str, Any]] = {}
            try:
                async with http.stream(
                    "POST",
                    url,
                    headers={
                        "Authorization": f"Bearer {cfg.deepseek_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": cfg.deepseek_model,
                        "messages": messages,
                        "tools": TOOLS,
                        "tool_choice": "auto",
                        "temperature": 0.1,
                        "stream": True,
                    },
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if not payload or payload == "[DONE]":
                            continue
                        try:
                            chunk = json.loads(payload)
                        except ValueError:
                            continue  # 心跳/注释行
                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        text = delta.get("content")
                        if text:
                            answer_parts.append(text)
                            yield {"type": "delta", "text": text}
                        _accumulate_tool_calls(calls, delta.get("tool_calls") or [])
            except httpx.HTTPError as exc:
                raise deepseek.DeepSeekUnavailable(f"DeepSeek Agent 调用失败：{exc}") from exc

            tool_calls = [calls[k] for k in sorted(calls)]
            if not tool_calls:
                yield {
                    "type": "done",
                    "result": {
                        "answer": "".join(answer_parts).strip(),
                        "steps": steps,
                        "model": cfg.deepseek_model,
                        "usedTools": [s["tool"] for s in steps],
                    },
                }
                return

            messages.append({
                "role": "assistant",
                "content": "".join(answer_parts),
                "tool_calls": tool_calls,
            })
            for call in tool_calls:
                fn = call.get("function") or {}
                name = str(fn.get("name", ""))
                args = _parse_args(fn.get("arguments"))
                result = execute(name, args)
                step = {
                    "tool": name, "args": args,
                    "result": result["structured"],
                    "callId": call.get("id", ""),
                }
                steps.append(step)
                yield {"type": "step", "step": step}
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "content": result["text"],
                })

        # 步数用尽仍未收敛：明确告知，不把截断冒充正常回答
        yield {
            "type": "done",
            "result": {
                "answer": "已查询知识库，但问题较复杂，工具调用达到上限。请缩小问题范围后重试，或直接查看下方工具返回的结果。",
                "steps": steps,
                "model": cfg.deepseek_model,
                "usedTools": [s["tool"] for s in steps],
                "truncated": True,
            },
        }
    finally:
        if owns_client:
            await http.aclose()
