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
import re
from typing import Any, AsyncIterator

import httpx

import checker

from . import deepseek, export_html, figures, styles, search as corpus_search

MAX_CONTEXT_BLOCKS = 24   # 交给模型的素材块上限（控制 token）
MAX_PER_QUERY = 6         # 每个检索词取多少行
CITES_LIMIT = 40          # 单段引用文本截断长度

COMPOSE_SYSTEM_PROMPT = """你是香港城市大学（东莞）媒体传讯处的公众号编辑。
你的任务：仅依据下面【素材库】里编号的内容，写一篇可直接使用的微信公众号文章草稿。

硬性要求：
1. 只能用【素材库】中的事实。每个正文段落末尾必须标注它依据的素材编号，如 [A1][A3]。
2. 素材库里没有的事实、数字、人名、日期一律不许写；宁可少写，不要编造或用常识补全。
3. 如果素材不足以支撑某个部分，在该部分写「（素材不足，待补充）」，不要虚构。
4. 严禁把截断片段当正文：不要输出「…」「……」或「素材原文截断」「待补充」等编辑批注。
   某句话在素材里不完整就整句不用，宁可少写一段，也不要照抄半句或补出解释。
5. 语言符合公众号文风：标题抓人但不夸张，导语短，正文分小标题，段落简洁。
6. 遵守给出的【写作规范】：标题与正文中校名首次出现写全称「香港城市大学（东莞）」，不要用「港城大」这类简称；
   集体提法「港澳台」必须写成「港澳台地区」或「港澳台同胞」，不能光写「港澳台」
   （但「港澳台侨联招」「港澳台办」这类专有名词照原样，不要改写成「港澳台地区侨联招」）；
   校领导姓名旁边要带职务全称（如「执行校长鲁春教授」「副校长（学术）李娟教授」），不要只写「副校长」；
   中文用全角标点。
7. 输出严格的 JSON（不要 markdown 代码块），结构如下：
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
8. cites 数组里只能填【素材库】中真实存在的编号；没有依据的段落 cites 留空并把 text 写为「（素材不足，待补充）」。
"""

REVISE_SYSTEM_PROMPT = """你是香港城市大学（东莞）媒体传讯处的公众号编辑，正在修改一篇已成型草稿。
任务：只按【修改指令】调整【当前草稿】，其余内容原样保留。

硬性要求：
1. 素材编号 A# 与当前草稿一致，cites 只能引用【素材库】里真实存在的编号，不许编新编号。
2. 不许引入素材库之外的事实、数字、人名、日期；原稿没有的事实依然不许补。
3. 指令没提到的标题、小标题、段落、配图建议逐字保留，不要顺手润色或重排结构。
4. 不许输出「…」「……」或「素材原文截断」「待补充」等编辑批注；不完整的句子直接删掉。
5. 按指令需要拆并段落时，cites 跟随内容迁移，不要丢失出处。
6. 输出完整的文章 JSON（不要 markdown 代码块），结构与当前草稿完全一致：
{"title": "", "lead": "", "sections": [{"heading": "", "paragraphs": [{"text": "", "cites": []}]}], "imageSuggestions": [{"after": "", "description": ""}]}
7. 遵守【写作规范】与【口径约束】；标题与正文里校名首次出现写全称「香港城市大学（东莞）」，
   不要为了标题简短改成「港城大」等简称。
8. 改稿时顺手守住两条口径：「港澳台」写全为「港澳台地区」/「港澳台同胞」（「港澳台侨联招」等专名除外）；
   校领导姓名旁带职务全称。
"""


def _title_hints(rules: list[dict]) -> str:
    """从 TITLE-001 规则生成「人物 → 规范职务」对照，附在系统提示里。

    素材原文常只写「副校长李娟教授」，模型照抄就踩 TITLE-001（少限定语）。硬编码
    一份对照表迟早和 rules 脱节，这里直接读规则里的 people/must_near 映射，规则改
    了提示自动跟着改。没有该规则时返回空串，不影响别的场景。
    """
    for rule in rules or []:
        if rule.get("id") != "TITLE-001":
            continue
        people = (rule.get("params") or {}).get("people") or []
        pairs = [
            f"{p['name']}={p['must_near'][0]}"
            for p in people
            if p.get("name") and p.get("must_near")
        ]
        if pairs:
            return (
                "【职务口径】素材里这些人的规范职务为 "
                + "、".join(pairs)
                + "。素材只写「副校长」「协理副校长」这类泛称时，按此补全限定语，属于规范要求，不算编造。\n"
            )
    return ""


def _dedup_search(query: str, limit: int) -> list[dict]:
    """整句混合检索（BM25 + 语义向量），不再拆词逐个 AND。

    旧实现把 query 拆成词逐个查，语义路永远拿不到整句，换一种说法就召回不到
    相关段落。现在整句入检，稀疏与稠密两路各取所需；去重交给 gather_material。
    """
    try:
        return corpus_search.search(query, limit=limit, mode="hybrid").get("results", [])
    except OSError:
        return []


def gather_material(topic: str, rules: list[dict]) -> tuple[list[dict], list[dict], dict]:
    """确定性检索：把选题变成素材编号，供模型引用。

    返回 (blocks, rule_items, meta)。blocks 每项含 ref / kind / text / file / line。
    """
    terms = deepseek._terms(topic, limit=8)
    # 整句混合检索是主力：语义路负责换词召回，BM25 负责词面精确命中。
    # 旧的「逐词 AND」会把「写一」「一篇」这类常见 2-gram 也拿去 BM25 查，
    # 反而召回一堆无关素材；只有整句结果明显不足时才用主题词补。
    raw: list[dict] = []
    seen: set[tuple[str, int]] = set()

    def collect(query: str, limit: int) -> None:
        for r in _dedup_search(query, limit):
            key = (r["file"], r["line"])
            if key in seen:
                continue
            seen.add(key)
            raw.append(r)

    collect(topic, MAX_CONTEXT_BLOCKS)
    if len(raw) < 8:
        for term in terms[:5]:
            if len(raw) >= MAX_CONTEXT_BLOCKS:
                break
            collect(term, MAX_PER_QUERY)
    # score 是 RRF 融合分（跨路可比），hits 只是兼容旧结果的词面命中数
    raw.sort(key=lambda r: -(r.get("score") or r.get("hits", 0)))

    blocks: list[dict] = []
    for r in raw[:MAX_CONTEXT_BLOCKS]:
        ref = f"A{len(blocks) + 1}"
        is_wx = r["file"].endswith("_WX")
        blocks.append({
            "ref": ref,
            "kind": "wechat" if is_wx else "archive",
            # 用完整块而不是 96 字摘要：摘要按首个查询词居中截取，
            # 关键事实常被切在窗口外，模型会误判「素材不足」。
            "text": r.get("text") or r["excerpt"],
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
    lines: list[str] = []
    brief = checker.authority_brief()
    if brief:
        lines.append("【口径约束】（非素材，不可作为 [A#] 引用）")
        lines.append(brief)
        lines.append("涉及上述口径时按权威值写；素材库若出现旧版数值，以此为准。")
        lines.append("")
    lines.append("【素材库】（每条的编号用于正文引用）")
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


# 模型经常把 [A1] 直接写进正文（而不是只放在 cites 里），前端再渲染一次角标
# 就会显示成「[A1] [A1]」。这里把正文里的标记剥出来并回填到 cites：
# 显示只出现一次，引用核对照样能发现无效编号。
INLINE_CITE_RE = re.compile(r"[\[［]\s*([A-Za-z])\s*(\d{1,3})\s*[\]］]")

# 兜底：模型偶尔仍会把被切断的素材句照抄进正文，连省略号和编辑批注一起带出来。
# 这种半成品不能发给编辑，整句丢掉比留半句更安全。
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?；;])")


def _drop_truncated_sentences(text: str) -> str:
    parts = _SENTENCE_SPLIT_RE.split(text)
    kept = [p for p in parts if "…" not in p and "素材原文截断" not in p]
    return "".join(kept).strip()


def _split_inline_cites(text: str) -> tuple[str, list[str]]:
    found = [f"{m.group(1)}{m.group(2)}".upper() for m in INLINE_CITE_RE.finditer(text)]
    cleaned = INLINE_CITE_RE.sub("", text)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip(), found


def parse_article(raw: str) -> dict:
    """把模型输出解析为结构化文章；非法结构降级为空草稿，不抛异常给调用方。"""
    try:
        data = json.loads(_strip_code_fence(raw))
    except (ValueError, TypeError):
        data = {}
    if not isinstance(data, dict):
        data = {}

    def clean_text(value: Any) -> str:
        if not isinstance(value, str):
            return ""
        return _drop_truncated_sentences(value.strip())

    sections: list[dict] = []
    for sec in data.get("sections") or []:
        if not isinstance(sec, dict):
            continue
        paragraphs: list[dict] = []
        for p in sec.get("paragraphs") or []:
            if not isinstance(p, dict):
                continue
            text, inline_cites = _split_inline_cites(clean_text(p.get("text")))
            cites: list[str] = []
            for ref in inline_cites + [
                str(c).strip().upper() for c in (p.get("cites") or []) if str(c).strip()
            ]:
                if ref not in cites:
                    cites.append(ref)
            paragraphs.append({"text": text, "cites": cites[:8]})
        heading, _ = _split_inline_cites(clean_text(sec.get("heading")))
        sections.append({
            "heading": heading,
            "paragraphs": paragraphs,
        })

    images: list[dict] = []
    for im in data.get("imageSuggestions") or []:
        if isinstance(im, dict):
            images.append({
                "after": clean_text(im.get("after")),
                "description": clean_text(im.get("description")),
            })

    # 标题与导语没有引用字段，正文标记直接摘掉，避免露出 [A1] 这种内部编号
    title, _ = _split_inline_cites(clean_text(data.get("title")))
    lead, _ = _split_inline_cites(clean_text(data.get("lead")))
    return {
        "title": title,
        "lead": lead,
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


async def _call_model_json(
    cfg: deepseek.Settings,
    system_prompt: str,
    user_prompt: str,
    client: httpx.AsyncClient | None,
) -> dict:
    """一次 JSON 模式成稿调用；失败统一转 DeepSeekUnavailable。"""
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
                    {"role": "system", "content": system_prompt},
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
        return parse_article(content)
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise deepseek.DeepSeekUnavailable(f"文章生成调用失败：{exc}") from exc
    finally:
        if owns_client:
            await http.aclose()


def attach_figures(article: dict) -> list[dict]:
    """从往期推文的真实照片里给每节配图；索引没建就当没有，不影响出稿。"""
    try:
        return figures.recommend(article.get("sections") or [])
    except figures.FigureIndexMissing:
        return []


def figures_to_markdown(figs: list[dict]) -> str:
    """导出 Markdown 只给配图位置与图注，不嵌真实图片链接。

    编辑拿这份稿子去公众号后台排版时，本来就该换成现场图/官方图；
    嵌本地 /api/figure 链接反而会贴出一个别人打不开的地址。
    """
    if not figs:
        return ""
    lines = ["---\n### 配图占位（图注来自往期推文配图，请按此替换成实拍图）\n"]
    for f in figs:
        warn = "（关联度一般，需人工确认）" if f.get("weak") else ""
        lines.append(
            f"- 第{f['sectionIndex'] + 1}节「{f['sectionHeading']}」："
            f"〔配图占位：{f['caption']}〕{warn}"
            f"　参考来源：《{f['sourceTitle']}》{f['sourcePublished']}"
        )
    return "\n".join(lines) + "\n"


async def _stream_model_raw(
    cfg: deepseek.Settings,
    system_prompt: str,
    user_prompt: str,
    client: httpx.AsyncClient | None,
) -> AsyncIterator[str]:
    """流式调用，按 DeepSeek 的 SSE 逐段吐原始文本（JSON 片段）。

    保留 JSON 模式：结构化输出的可靠性比"好看的流"重要，前端另做增量解析。
    """
    url = f"{cfg.deepseek_base_url.rstrip('/')}/chat/completions"
    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=180)
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
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.3,
                "stream": True,
                "response_format": {"type": "json_object"},
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
                    # 心跳/注释行，跳过即可，不中断整篇
                    continue
                choices = chunk.get("choices") or []
                if not choices:
                    continue
                text = (choices[0].get("delta") or {}).get("content")
                if text:
                    yield text
    except httpx.HTTPError as exc:
        raise deepseek.DeepSeekUnavailable(f"文章生成调用失败：{exc}") from exc
    finally:
        if owns_client:
            await http.aclose()


def _prepare(
    topic: str,
    rules: list[dict],
    style: str,
    settings: deepseek.Settings | None = None,
) -> dict:
    """两条路径（一次性 / 流式）共用的准备：定文体、检索素材、拼两份提示。"""
    cfg = settings or deepseek.get_settings()
    if not cfg.configured:
        raise deepseek.DeepSeekNotConfigured("未配置 DEEPSEEK_API_KEY，请在 campus-kb/.env 中填入密钥")

    spec = styles.resolve_style(style, topic)
    blocks, rule_items, meta = gather_material(topic, rules)
    meta["style"] = spec["id"]
    context = build_context(blocks, rule_items)
    return {
        "cfg": cfg,
        "spec": spec,
        "blocks": blocks,
        "rule_items": rule_items,
        "meta": meta,
        "user_prompt": f"请围绕选题写公众号文章草稿。\n选题：{topic}\n\n{context}",
        "system_prompt": f"{COMPOSE_SYSTEM_PROMPT}\n\n{_title_hints(rules)}{styles.style_block(spec)}",
    }


def _assemble(
    topic: str,
    article: dict,
    ctx: dict,
    rules: list[dict],
    style: str,
) -> dict:
    """模型写完之后的所有确定性收尾：引用核对、发前检查、配图、导出格式。"""
    cites = check_citations(article, ctx["blocks"])
    review = review_article(article, rules)
    figs = attach_figures(article)
    return {
        "topic": topic,
        "article": article,
        "markdown": article_to_markdown(article) + figures_to_markdown(figs),
        "html": export_html.article_to_html(article, figs),
        "sources": ctx["blocks"],
        "rules": ctx["rule_items"],
        "meta": ctx["meta"],
        "citations": cites,
        "review": review,
        "style": styles.style_meta(ctx["spec"], style),
        "figures": figs,
        "model": ctx["cfg"].deepseek_model,
    }


async def compose_article(
    topic: str,
    rules: list[dict],
    settings: deepseek.Settings | None = None,
    client: httpx.AsyncClient | None = None,
    style: str = "auto",
) -> dict:
    """主流程：定文体 → 检索 → 成稿 → 校验出处与规范。返回可直接下发前端的结构。"""
    ctx = _prepare(topic, rules, style, settings)
    article = await _call_model_json(ctx["cfg"], ctx["system_prompt"], ctx["user_prompt"], client)
    return _assemble(topic, article, ctx, rules, style)


async def compose_article_stream(
    topic: str,
    rules: list[dict],
    settings: deepseek.Settings | None = None,
    client: httpx.AsyncClient | None = None,
    style: str = "auto",
) -> AsyncIterator[dict]:
    """流式成稿：先吐模型原始增量，收尾时再给完整结果。

    事件：`meta`（文体）→ 若干 `delta`（JSON 片段）→ `done`（完整结果，同 /api/compose）。
    检索与提示准备发生在第一个事件之前，所以首帧前会有一两秒静默。
    """
    ctx = _prepare(topic, rules, style, settings)
    yield {"type": "meta", "style": styles.style_meta(ctx["spec"], style)}

    buf: list[str] = []
    async for delta in _stream_model_raw(ctx["cfg"], ctx["system_prompt"], ctx["user_prompt"], client):
        buf.append(delta)
        yield {"type": "delta", "text": delta}

    raw = "".join(buf)
    article = parse_article(raw)
    if not article.get("sections"):
        # 流被截断或模型跑飞：宁可报错让用户重试，也不要下发一篇空稿
        raise deepseek.DeepSeekUnavailable("模型返回内容不完整，请重试")
    yield {"type": "done", "result": _assemble(topic, article, ctx, rules, style)}


async def revise_article(
    topic: str,
    article: dict,
    instruction: str,
    blocks: list[dict],
    rule_items: list[dict],
    rules: list[dict],
    settings: deepseek.Settings | None = None,
    client: httpx.AsyncClient | None = None,
    style: str = "auto",
) -> dict:
    """在已有草稿上按指令改稿：素材编号与出处不变，只重跑引用与规范校验。

    不复用 gather_material：改稿要沿用同一批编号素材，重新检索会让正文里的
    [A3] 指到别的内容，引用核对随即失真。文体也要带上——只给指令不给文体，
    模型容易把致辞改成新闻腔。
    """
    cfg = settings or deepseek.get_settings()
    if not cfg.configured:
        raise deepseek.DeepSeekNotConfigured("未配置 DEEPSEEK_API_KEY，请在 campus-kb/.env 中填入密钥")

    spec = styles.resolve_style(style, topic or str(article.get("title", "")))
    context = build_context(blocks, rule_items)
    user_prompt = (
        f"【修改指令】{instruction}\n\n"
        f"【当前草稿】\n{json.dumps(article, ensure_ascii=False, indent=2)}\n\n"
        f"{context}"
    )
    system_prompt = f"{REVISE_SYSTEM_PROMPT}\n\n{_title_hints(rules)}{styles.style_block(spec)}"

    revised = await _call_model_json(cfg, system_prompt, user_prompt, client)
    # 模型偶发返回空结构：保留原稿，不要拿空白覆盖用户已认可的版本
    if not revised.get("sections"):
        revised = {**article, "sections": article.get("sections", [])}

    cites = check_citations(revised, blocks)
    review = review_article(revised, rules)
    figs = attach_figures(revised)
    return {
        "topic": topic,
        "instruction": instruction,
        "article": revised,
        "markdown": article_to_markdown(revised) + figures_to_markdown(figs),
        "html": export_html.article_to_html(revised, figs),
        "sources": blocks,
        "rules": rule_items,
        "meta": {"terms": [], "scanned": 0, "revised": True},
        "citations": cites,
        "review": review,
        "style": styles.style_meta(spec, style),
        "figures": figs,
        "model": cfg.deepseek_model,
    }
