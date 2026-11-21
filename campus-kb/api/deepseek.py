"""DeepSeek 问答层：把知识库片段作为上下文交给大模型做解读与自由问答。

红线：确定性校验仍由 checker.py 负责。本模块不判断稿件是否合规，
只基于检索到的规则/档案片段回答开放问题；片段不足时明确说不知道。

配置见 campus-kb/.env.example，密钥从 DEEPSEEK_API_KEY 读取。
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import httpx
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from . import search as corpus_search

KB = Path(__file__).resolve().parent.parent

SYSTEM_PROMPT = """你是香港城市大学（东莞）媒体传讯处知识库的助手。
只依据下面【知识库片段】回答用户问题，并在引用处标注片段编号，如 [S1]、[A1]。

- 片段没有依据时，明确说「知识库中没有找到足够依据」，不要凭常识猜测或编造。
- 涉及稿件是否符合规范的问题，以规则引擎的确定性校验为准，不要把你的判断说成规则结论。
- 回答用简洁中文，不要输出与问题无关的内容。

【知识库片段】
{context}
"""


class DeepSeekNotConfigured(RuntimeError):
    """未配置密钥：可明确提示用户，不是服务故障。"""


class DeepSeekUnavailable(RuntimeError):
    """模型调用失败：网络、鉴权或上游错误。"""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(KB / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    deepseek_api_key: str = Field(default="", description="DeepSeek API Key")
    deepseek_model: str = Field(default="deepseek-chat")
    deepseek_base_url: str = Field(default="https://api.deepseek.com")

    @property
    def configured(self) -> bool:
        return bool(self.deepseek_api_key.strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """配置进程内只读一次；测试改环境变量后调用 cache_clear() 即可。"""
    return Settings()


def _terms(text: str, limit: int = 12) -> list[str]:
    """提取检索词：英文按词，中文按 2-gram，避免整句 AND 检索必然落空。"""
    parts = re.findall(r"[a-zA-Z0-9]+|[\u4e00-\u9fff]+", text.lower())
    out: list[str] = []
    for part in parts:
        if part[0].isalnum() and not "\u4e00" <= part[0] <= "\u9fff":
            if len(part) > 1:
                out.append(part)
        elif len(part) == 1:
            out.append(part)
        else:
            out.extend(part[i : i + 2] for i in range(len(part) - 1))

    seen: set[str] = set()
    uniq: list[str] = []
    for term in out:
        if term not in seen:
            seen.add(term)
            uniq.append(term)
    return uniq[:limit]


def _score(text: str, terms: list[str]) -> int:
    low = text.lower()
    return sum(1 for t in terms if t in low)


def build_context(
    question: str,
    rules: list[dict],
    limit_rules: int = 5,
    limit_archive: int = 5,
) -> tuple[str, list[dict]]:
    """检索规则与档案片段，返回 (拼好的上下文文本, 供前端展示的来源列表)。"""
    terms = _terms(question)
    blocks: list[str] = []
    sources: list[dict] = []

    if not terms:
        return "（问题中没有可检索的关键词）", sources

    scored_rules: list[tuple[int, dict]] = []
    for rule in rules:
        hay = " ".join(
            str(rule.get(k, "")) for k in ("id", "category", "desc", "suggestion", "type")
        )
        hit = _score(hay, terms)
        if hit:
            scored_rules.append((hit, rule))
    scored_rules.sort(key=lambda x: -x[0])

    for _hit, rule in scored_rules[:limit_rules]:
        ref = f"S{len(sources) + 1}"
        desc = f"[{rule['id']}] {rule['desc']}"
        suggestion = rule.get("suggestion", "")
        detail = f"{desc}；建议：{suggestion}" if suggestion else desc
        sources.append({"ref": ref, "kind": "rule", "title": rule["id"], "detail": detail})
        blocks.append(f"[{ref}] {detail}")

    archive: list[tuple[int, str, int, str]] = []
    try:
        docs = corpus_search.load_corpus(str(corpus_search.corpus_dir()))
    except OSError:
        docs = ()
    for doc in docs:
        if not _score(doc.text, terms):
            continue
        lines = doc.text.split("\n")
        line_no, line = max(enumerate(lines, 1), key=lambda pair: _score(pair[1], terms))
        if _score(line, terms):
            archive.append((_score(doc.text, terms), doc.name, line_no, line.strip()))
    archive.sort(key=lambda x: -x[0])

    for _hit, name, line_no, line in archive[:limit_archive]:
        ref = f"A{len(sources) + 1}"
        excerpt = line[:160] + ("…" if len(line) > 160 else "")
        detail = f"{name} · 第 {line_no} 行：{excerpt}"
        sources.append({"ref": ref, "kind": "archive", "title": name, "detail": detail})
        blocks.append(f"[{ref}] {detail}")

    if not blocks:
        return "（知识库中未检索到相关片段）", sources
    return "\n".join(blocks), sources


async def ask(
    question: str,
    rules: list[dict],
    history: list[dict] | None = None,
    settings: Settings | None = None,
) -> dict:
    """调 DeepSeek chat/completions；返回模型回答与本次引用的知识库来源。"""
    cfg = settings or get_settings()
    if not cfg.configured:
        raise DeepSeekNotConfigured("未配置 DEEPSEEK_API_KEY，请在 campus-kb/.env 中填入密钥")

    context, sources = build_context(question, rules)
    messages: list[dict[str, str]] = [
        {"role": "system", "content": SYSTEM_PROMPT.format(context=context)}
    ]
    for turn in (history or [])[-6:]:
        if turn.get("role") in ("user", "assistant") and isinstance(turn.get("content"), str):
            messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": question})

    url = f"{cfg.deepseek_base_url.rstrip('/')}/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {cfg.deepseek_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": cfg.deepseek_model,
                    "messages": messages,
                    "temperature": 0.2,
                    "stream": False,
                },
            )
            response.raise_for_status()
            data = response.json()
        answer = data["choices"][0]["message"]["content"].strip()
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise DeepSeekUnavailable(f"DeepSeek 调用失败：{exc}") from exc

    return {"answer": answer, "sources": sources, "model": cfg.deepseek_model}
