"""一键成稿流水线：检索 → Agent 成稿 → 发前检查 → 自动修订 → 排版导出。

这是项目主线（RAG 知识库 + Agent → 可直发公众号文章）的最终形态：用户只给
一句话，后端把中间环节全部串完，最终直接给出可复制的干净稿。

职责边界（与 compose.py 一致，不重复实现）：
- 事实与出处来自确定性检索，校验结论来自 checker.py 规则引擎；
- 模型只做两件事：按编号素材写稿、按明确指令改稿；
- 本模块只负责编排顺序、发 SSE 步骤事件、在 error 级命中时自动修订一轮。

SSE 事件序列：
  meta    planned 步骤清单 + 文体
  step    某一步完成（含 detail）
  delta   成稿模型原文增量（JSON 片段，前端增量解析）
  done    完整结果（结构同 /api/compose，额外带 pipeline 轨迹）

自动修订只在发前检查有 error 时触发一轮，最多一次，避免无限往返烧 token。
"""

from __future__ import annotations

from typing import Any, AsyncIterator

import httpx

from . import compose, deepseek, export_html, styles

# 计划步骤：revise 是条件步骤，触发时即时插入，不预先写进 planned
PLANNED_STEPS: list[dict[str, str]] = [
    {"id": "retrieve", "label": "检索语料"},
    {"id": "compose", "label": "Agent 成稿"},
    {"id": "review", "label": "发前检查"},
    {"id": "export", "label": "排版导出"},
]

MAX_REVISIONS = 1
MAX_ISSUES_IN_INSTRUCTION = 5


def revise_instruction(review: dict, max_items: int = MAX_ISSUES_IN_INSTRUCTION) -> str:
    """把 error 级命中转成改稿指令；没有 error 时返回空串，不触发修订。"""
    errors = [f for f in review.get("findings", []) if f.get("severity") == "error"]
    if not errors:
        return ""
    lines = ["发前检查发现以下规范问题，请按建议逐条修正，未点名的内容保持原样："]
    for f in errors[:max_items]:
        line = f"第{f.get('line')}行 {f.get('ruleId')}：{f.get('message')}"
        if f.get("suggestion"):
            line += f"；建议：{f['suggestion']}"
        lines.append(line)
    return "\n".join(lines)


def _strip_internal_fields(result: dict) -> dict:
    """done 结果与 /api/compose 对齐；修订接口带的 instruction 不属成稿结构。"""
    out = dict(result)
    out.pop("instruction", None)
    return out


async def run_pipeline_stream(
    topic: str,
    rules: list[dict],
    settings: deepseek.Settings | None = None,
    client: httpx.AsyncClient | None = None,
    style: str = "auto",
    auto_revise: bool = True,
) -> AsyncIterator[dict]:
    """端到端成稿，逐步发步骤事件；最终 done 的 result 可直接下发前端。"""
    # 1. 检索（确定性）：定文体 + 混合检索素材 + 拼提示
    ctx = compose._prepare(topic, rules, style, settings)
    yield {
        "type": "meta",
        "style": styles.style_meta(ctx["spec"], style),
        "steps": PLANNED_STEPS,
        "sourceCount": len(ctx["blocks"]),
    }
    yield {
        "type": "step",
        "id": "retrieve",
        "label": "检索语料",
        "detail": f"命中 {len(ctx['blocks'])} 条素材 · 检索词 {'、'.join(ctx['meta'].get('terms') or [])[:60]}",
    }

    # 2. 成稿（模型）：复用流式调用，逐字吐原始 JSON 片段
    buf: list[str] = []
    async for delta in compose._stream_model_raw(
        ctx["cfg"], ctx["system_prompt"], ctx["user_prompt"], client
    ):
        buf.append(delta)
        yield {"type": "delta", "text": delta}

    article = compose.parse_article("".join(buf))
    if not article.get("sections"):
        raise deepseek.DeepSeekUnavailable("模型返回内容不完整，请重试")
    prepared = compose.check_citations(article, ctx["blocks"])
    paragraph_count = prepared.get("paragraphCount", 0)
    yield {
        "type": "step",
        "id": "compose",
        "label": "Agent 成稿",
        "detail": f"完成 {paragraph_count} 个有据段落",
    }

    # 3. 发前检查（确定性规则引擎）：先组装一次，拿到 review 再决定是否修订
    result = compose._assemble(topic, article, ctx, rules, style)
    initial_counts = dict(result["review"]["counts"])
    yield {
        "type": "step",
        "id": "review",
        "label": "发前检查",
        "detail": f"{initial_counts.get('error', 0)} 错 / {initial_counts.get('warn', 0)} 警",
        "review": result["review"],
    }

    # 4. 自动修订（模型）：只在 error 级命中时转一轮，避免把 warn 也当错误改
    trace: list[dict[str, Any]] = []
    if auto_revise and initial_counts.get("error", 0) > 0:
        instruction = revise_instruction(result["review"])
        if instruction:
            yield {
                "type": "step",
                "id": "revise",
                "label": "自动修订",
                "detail": f"修正 {initial_counts['error']} 项规范问题",
            }
            for _ in range(MAX_REVISIONS):
                revised = await compose.revise_article(
                    topic,
                    result["article"],
                    instruction,
                    ctx["blocks"],
                    ctx["rule_items"],
                    rules,
                    settings=ctx["cfg"],
                    client=client,
                    style=style,
                )
                result = revised
                trace.append({
                    "instruction": instruction,
                    "before": initial_counts,
                    "after": dict(revised["review"]["counts"]),
                })

    # 5. 排版导出：_assemble / revise_article 已生成 markdown 与内联样式 HTML
    html = result.get("html", "")
    yield {
        "type": "step",
        "id": "export",
        "label": "排版导出",
        "detail": f"内联样式 HTML 已就绪 · {len(html)} 字符",
    }

    final = _strip_internal_fields(result)
    final["pipeline"] = {
        "autoRevise": auto_revise,
        "revisions": trace,
        "finalCounts": result["review"]["counts"],
    }
    yield {"type": "done", "result": final}
