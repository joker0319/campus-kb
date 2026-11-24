"""公众号文章生成：检索知识库 → 模型成稿 → 后端校验出处与规范。

主线功能（项目的 P0）：把 Agent 从「检索问答」升级为「产出成稿」。

流水线三段，职责严格分开：
  1. 检索（确定性）：按选题从档案 / 往期推文检索带文件名+行号的片段，
     再取相关写作规范。给模型的每条素材都编号 A1../R1..，出处随片段走。
  2. 成稿（模型）：DeepSeek 只用编号素材写结构化文章，每个段落必须带 [A#] 引用；
     没有依据的内容不写，查不到就明说。模型不产出校验结论。
  3. 校验（确定性）：后端核对引用编号是否真实存在、段落是否无出处，
     并把成稿正文交给 checker.py 规则引擎跑一遍，命中作为「发前检查」返回。

红线：模型只组织语言，事实与出处来自检索结果；无法溯源的内容会被标记，
不冒充有据。配置与密钥复用 deepseek.Settings。
"""

from __future__ import annotations

import json
from typing import Any

import httpx

import checker

from . import deepseek, search as corpus_search

MAX_CONTEXT_BLOCKS = 24   # 交给模型的素材块上限（控制 token）
MAX_PER_QUERY = 6         # 每个检索词取多少行
CITES_LIMIT = 40          # 单段引用文本截断长度

COMPOSE_SYSTEM_PROMPT = """你是香港城市大学（东莞）媒体传讯处的公众号编辑。
你的任务：仅依据下面【素材库】里编号的内容，写一篇可直接使用的微信公众号文章草稿。

硬性要求：
1. 只能用【素材库】中的事实。每个正文段落末尾必须标注它依据的素材编号，如 [A1][A3]。
2. 素材库里没有的事实、数字、人名、日期一律不许写；宁可少写，不要编造或用常识补全。
3. 如果素材不足以支撑某个部分，在该部分写「（素材不足，待补充）」，不要虚构。
4. 语言符合公众号文风：标题抓人但不夸张，导语短，正文分小标题，段落简洁。
5. 遵守给出的【写作规范】：校名首次全称、中文全角标点等。
6. 输出严格的 JSON（不要 markdown 代码块），结构如下：
{
  "title": "文章标题",
  "lead": "导语，100 字以内",
  "sections": [
    {"heading": "小标题", "paragraphs": [
      {"text": "段落正文", "cites": ["A1", "A3"]}
    ]}
  ],
  "imageSuggestions": [{"after": "小标题或段落序号", "description": "建议配图内容"}]
}
7. cites 数组里只能填【素材库】中真实存在的编号；没有依据的段落 cites 留空并把 text 写为「（素材不足，待补充）」。
"""


def _dedup_search(query: str, limit: int) -> list[dict]:
    """按单个检索词检索，去重（同一 file+line 只留一条）。"""
    out: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for term in query.split():
        try:
            result = corpus_search.search(term, limit=limit)
        except OSError:
            continue
        for r in result.get("results", []):
            key = (r["file"], r["line"])
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
    return out


def gather_material(topic: str, rules: list[dict]) -> tuple[list[dict], list[dict], dict]:
    """确定性检索：把选题变成素材编号，供模型引用。

    返回 (blocks, rule_items, meta)。blocks 每项含 ref / kind / text / file / line。
    """
    terms = deepseek._terms(topic, limit=8)
    # 主题整句优先，其次各检索词；再去重按命中数排序
    queries = [topic] + terms[:5]
    raw: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for q in queries:
        for r in _dedup_search(q, MAX_PER_QUERY):
            key = (r["file"], r["line"])
            if key in seen:
                continue
            seen.add(key)
            raw.append(r)
        if len(raw) >= MAX_CONTEXT_BLOCKS:
            break
    raw.sort(key=lambda r: -r.get("hits", 0))

    blocks: list[dict] = []
    for r in raw[:MAX_CONTEXT_BLOCKS]:
        ref = f"A{len(blocks) + 1}"
        is_wx = r["file"].endswith("_WX")
        blocks.append({
            "ref": ref,
            "kind": "wechat" if is_wx else "archive",
            "text": r["excerpt"],
            "file": r["file"] + ".txt",
            "line": r["line"],
        })

    # 写作规范：用主题词对规则打分，取最相关的几条作为风格约束
    scored: list[tuple[int, dict]] = []
    for rule in rules:
        hay = " ".join(str(rule.get(k, "")) for k in ("id", "desc", "suggestion", "category"))
        hit = deepseek._score(hay, terms)
        if hit:
            scored.append((hit, rule))
    scored.sort(key=lambda x: -x[0])
    rule_items: list[dict] = []
    for _hit, rule in scored[:6]:
        rid = f"R{len(rule_items) + 1}"
        rule_items.append({
            "ref": rid,
            "id": rule["id"],
            "text": rule["desc"] + (f"；建议：{rule['suggestion']}" if rule.get("suggestion") else ""),
            "source": rule.get("source", ""),
        })

    return blocks, rule_items, {
        "terms": terms,
        "scanned": len(corpus_search.load_corpus(str(corpus_search.corpus_dir()))),
    }


def build_context(blocks: list[dict], rule_items: list[dict]) -> str:
    lines = ["【素材库】（每条的编号用于正文引用）"]
    for b in blocks:
        lines.append(f"- [{b['ref']}] {b['text']}（来源：{b['file']} 第 {b['line']} 行）")
    if not blocks:
        lines.append("- （素材库为空：知识库中未检索到与该选题相关的记录）")
    lines.append("\n【写作规范】（写稿时遵守）")
    for r in rule_items:
        lines.append(f"- [{r['ref']}] {r['id']}：{r['text']}")
    if not rule_items:
        lines.append("- （未匹配到特定写作规范，仍须遵守校名全称与中文全角标点的通用要求）")
    return "\n".join(lines)


def _strip_code_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1]
        if t.endswith("```"):
            t = t.rsplit("```", 1)[0]
    return t.strip()


def parse_article(raw: str) -> dict:
    """把模型输出解析为结构化文章；非法结构降级为空草稿，不抛异常给调用方。"""
    try:
        data = json.loads(_strip_code_fence(raw))
    except (ValueError, TypeError):
        data = {}
    if not isinstance(data, dict):
        data = {}

    def clean_text(value: Any) -> str:
        return value.strip() if isinstance(value, str) else ""

    sections: list[dict] = []
    for sec in data.get("sections") or []:
        if not isinstance(sec, dict):
            continue
        paragraphs: list[dict] = []
        for p in sec.get("paragraphs") or []:
            if not isinstance(p, dict):
                continue
            cites = [str(c).strip().upper() for c in (p.get("cites") or []) if str(c).strip()]
            paragraphs.append({"text": clean_text(p.get("text")), "cites": cites[:8]})
        sections.append({
            "heading": clean_text(sec.get("heading")),
            "paragraphs": paragraphs,
        })

    images: list[dict] = []
    for im in data.get("imageSuggestions") or []:
        if isinstance(im, dict):
            images.append({
                "after": clean_text(im.get("after")),
                "description": clean_text(im.get("description")),
            })

    return {
        "title": clean_text(data.get("title")),
        "lead": clean_text(data.get("lead")),
        "sections": sections,
        "imageSuggestions": images,
    }


def check_citations(article: dict, blocks: list[dict]) -> dict:
    """后端核对引用：无效编号 / 无出处段落都要暴露给用户，不冒充有据。"""
    valid = {b["ref"] for b in blocks}
    cited_counts: dict[str, int] = {}
    uncited = 0
    invalid: list[str] = []
    total = 0
    for sec in article.get("sections", []):
        for p in sec.get("paragraphs", []):
            text = p.get("text", "")
            if not text or text.startswith("（素材不足"):
                continue
            total += 1
            cites = p.get("cites", [])
            if not cites:
                uncited += 1
            for c in cites:
                if c in valid:
                    cited_counts[c] = cited_counts.get(c, 0) + 1
                elif c not in invalid:
                    invalid.append(c)
    used = [b for b in blocks if b["ref"] in cited_counts]
    return {
        "cited": used,
        "uncitedParagraphs": uncited,
        "invalidCites": invalid,
        "paragraphCount": total,
        "grounded": total > 0 and uncited == 0 and not invalid,
    }


def review_article(article: dict, rules: list[dict]) -> dict:
    """把成稿正文交给规则引擎做发前检查（校验是项目的一个功能，不是主线）。"""
    parts = [article.get("title", ""), article.get("lead", "")]
    for sec in article.get("sections", []):
        if sec.get("heading"):
            parts.append(sec["heading"])
        for p in sec.get("paragraphs", []):
            if p.get("text"):
                parts.append(p["text"])
    body = "\n".join(x for x in parts if x)
    if not body:
        return {"counts": {"total": 0, "error": 0, "warn": 0, "info": 0}, "findings": []}
    # 用 archive 模式：公众号文章不是投稿件，SUB-* 投稿格式规则（标题格式 /
    # 英文标注 / 内容分类勾选）不适用，跳过；只保留 NAME/PUNCT 等内容规范。
    findings = checker.run(body, rules, mode="archive")
    counts = {"total": len(findings), "error": 0, "warn": 0, "info": 0}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    out = [{
        "ruleId": f["rule_id"], "line": f["line"], "severity": f["severity"],
        "message": f["message"], "suggestion": f.get("suggestion", ""),
    } for f in findings[:30]]
    return {"counts": counts, "findings": out}


def article_to_markdown(article: dict) -> str:
    """结构化草稿 → 可直接复制到公众号后台的 Markdown。"""
    lines: list[str] = []
    if article.get("title"):
        lines.append(f"# {article['title']}\n")
    if article.get("lead"):
        lines.append(f"{article['lead']}\n")
    for sec in article.get("sections", []):
        if sec.get("heading"):
            lines.append(f"## {sec['heading']}\n")
        for p in sec.get("paragraphs", []):
            if p.get("text"):
                cites = " ".join(f"[{c}]" for c in p.get("cites", []))
                lines.append(p["text"] + (f" {cites}" if cites else "") + "\n")
    if article.get("imageSuggestions"):
        lines.append("---\n### 配图建议\n")
        for im in article["imageSuggestions"]:
            lines.append(f"- {im.get('after', '')}：{im.get('description', '')}")
    return "\n".join(lines).strip() + "\n"


async def compose_article(
    topic: str,
    rules: list[dict],
    settings: deepseek.Settings | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict:
    """主流程：检索 → 成稿 → 校验出处与规范。返回可直接下发前端的结构。"""
    cfg = settings or deepseek.get_settings()
    if not cfg.configured:
        raise deepseek.DeepSeekNotConfigured("未配置 DEEPSEEK_API_KEY，请在 campus-kb/.env 中填入密钥")

    blocks, rule_items, meta = gather_material(topic, rules)
    context = build_context(blocks, rule_items)
    user_prompt = f"请围绕选题写公众号文章草稿。\n选题：{topic}\n\n{context}"

    url = f"{cfg.deepseek_base_url.rstrip('/')}/chat/completions"
    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=120)
    try:
        response = await http.post(
            url,
            headers={"Authorization": f"Bearer {cfg.deepseek_api_key}", "Content-Type": "application/json"},
            json={
                "model": cfg.deepseek_model,
                "messages": [
                    {"role": "system", "content": COMPOSE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.3,
                "stream": False,
                "response_format": {"type": "json_object"},
            },
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"].get("content") or ""
        article = parse_article(content)
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise deepseek.DeepSeekUnavailable(f"文章生成调用失败：{exc}") from exc
    finally:
        if owns_client:
            await http.aclose()

    cites = check_citations(article, blocks)
    review = review_article(article, rules)
    return {
        "topic": topic,
        "article": article,
        "markdown": article_to_markdown(article),
        "sources": blocks,
        "rules": rule_items,
        "meta": meta,
        "citations": cites,
        "review": review,
        "model": cfg.deepseek_model,
    }
