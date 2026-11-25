"""一键流水线：事件序列、自动修订开关、错误帧。"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api import compose, deepseek, main as main_mod, pipeline
from api.deepseek import Settings

ARTICLE_JSON = (
    '{"title":"报到指引",'
    '"sections":[{"heading":"一","paragraphs":[{"text":"正文。","cites":["A1"]}]}]}'
)


def _base_result(error_count: int = 0) -> dict[str, Any]:
    return {
        "topic": "新生报到",
        "article": {"title": "报到指引", "lead": "", "sections": [], "imageSuggestions": []},
        "markdown": "# 报到指引",
        "html": "<section>ok</section>",
        "sources": [],
        "rules": [],
        "meta": {"terms": [], "scanned": 0, "style": "news"},
        "citations": {"grounded": True, "paragraphCount": 1},
        "review": {
            "counts": {"total": error_count, "error": error_count, "warn": 0, "info": 0},
            "findings": [
                {"ruleId": "NAME-001", "line": 3, "severity": "error", "message": "校名", "suggestion": "写全称"}
                for _ in range(error_count)
            ],
        },
        "style": {"id": "news", "name": "新闻动态", "auto": True},
        "figures": [],
        "model": "deepseek-chat",
    }


def _patch_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    error_count: int = 0,
    revised_errors: int = 0,
) -> list[str]:
    """替掉编排依赖的 compose 函数，返回修订调用记录里的指令列表。"""
    ctx = {
        "cfg": Settings(deepseek_api_key="test-key"),
        "spec": {"id": "news", "name": "新闻动态"},
        "blocks": [{"ref": "A1", "text": "素材", "file": "x.txt", "line": 1}],
        "rule_items": [],
        "meta": {"terms": ["报到"], "scanned": 1, "style": "news"},
        "user_prompt": "u",
        "system_prompt": "s",
    }
    monkeypatch.setattr(compose, "_prepare", lambda *a, **k: ctx)

    async def fake_raw(*a: Any, **k: Any):
        yield ARTICLE_JSON[:10]
        yield ARTICLE_JSON[10:]

    monkeypatch.setattr(compose, "_stream_model_raw", fake_raw)
    initial = _base_result(error_count)

    def fake_assemble(*a: Any, **k: Any) -> dict[str, Any]:
        return json.loads(json.dumps(initial))  # 深拷贝，避免修订后影响断言

    monkeypatch.setattr(compose, "_assemble", fake_assemble)

    revised = _base_result(revised_errors)
    revised["article"]["title"] = "修订后标题"
    revised["instruction"] = "自动修订指令"
    calls: list[str] = []

    async def fake_revise(*a: Any, **k: Any) -> dict[str, Any]:
        calls.append(str(a[2]))  # instruction 是第三个位置参数
        return json.loads(json.dumps(revised))

    monkeypatch.setattr(compose, "revise_article", fake_revise)
    return calls


def _collect(topic: str = "新生报到", auto_revise: bool = True) -> list[dict]:
    async def run() -> list[dict]:
        return [e async for e in pipeline.run_pipeline_stream(topic, [], auto_revise=auto_revise)]

    return asyncio.run(run())


def test_pipeline_event_sequence(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_pipeline(monkeypatch, error_count=0)

    events = _collect()

    types = [e["type"] for e in events]
    assert types[0] == "meta"
    assert [s["id"] for s in events[0]["steps"]] == ["retrieve", "compose", "review", "export"]
    assert events[1]["id"] == "retrieve"
    # delta 夹在 retrieve / compose 两个 step 之间
    step_ids = [e.get("id") for e in events if e["type"] == "step"]
    assert step_ids == ["retrieve", "compose", "review", "export"]
    assert any(e["type"] == "delta" for e in events)
    assert events[-1]["type"] == "done"
    result = events[-1]["result"]
    assert result["article"]["title"] == "报到指引"
    assert result["html"]
    assert result["pipeline"]["revisions"] == []


def test_pipeline_auto_revises_once_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_pipeline(monkeypatch, error_count=2, revised_errors=0)

    events = _collect()

    step_ids = [e.get("id") for e in events if e["type"] == "step"]
    assert "revise" in step_ids
    assert step_ids.count("revise") == 1  # 最多一轮
    assert len(calls) == 1
    assert "NAME-001" in calls[0]
    result = events[-1]["result"]
    assert result["article"]["title"] == "修订后标题"
    assert "instruction" not in result  # 内部字段不下发
    assert result["pipeline"]["revisions"][0]["before"]["error"] == 2
    assert result["pipeline"]["revisions"][0]["after"]["error"] == 0


def test_pipeline_auto_revise_can_be_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_pipeline(monkeypatch, error_count=1)

    events = _collect(auto_revise=False)

    step_ids = [e.get("id") for e in events if e["type"] == "step"]
    assert "revise" not in step_ids
    assert calls == []
    assert events[-1]["result"]["pipeline"]["autoRevise"] is False


def _sse_frames(text: str) -> list[dict]:
    frames = []
    for block in text.split("\n\n"):
        line = next((ln for ln in block.splitlines() if ln.startswith("data:")), None)
        if line:
            frames.append(json.loads(line[5:].strip()))
    return frames


def test_pipeline_endpoint_serializes_events(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(deepseek, "get_settings", lambda: Settings(deepseek_api_key="test-key"))

    async def fake_run(*a: Any, **k: Any):
        yield {"type": "meta", "steps": [], "style": {}}
        yield {"type": "step", "id": "retrieve", "label": "检索语料", "detail": "ok"}
        yield {"type": "done", "result": {"article": {"title": "x"}}}

    monkeypatch.setattr(main_mod.pipeline, "run_pipeline_stream", fake_run)

    resp = TestClient(main_mod.app).post("/api/pipeline/stream", json={"topic": "新生报到"})

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert resp.headers["x-accel-buffering"] == "no"
    assert [f["type"] for f in _sse_frames(resp.text)] == ["meta", "step", "done"]


def test_pipeline_endpoint_returns_503_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(deepseek, "get_settings", lambda: Settings(deepseek_api_key=""))
    resp = TestClient(main_mod.app).post("/api/pipeline/stream", json={"topic": "新生报到"})
    assert resp.status_code == 503


def test_pipeline_endpoint_sends_error_event(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(deepseek, "get_settings", lambda: Settings(deepseek_api_key="test-key"))

    async def failing(*a: Any, **k: Any):
        yield {"type": "meta", "steps": [], "style": {}}
        raise deepseek.DeepSeekUnavailable("上游超时")

    monkeypatch.setattr(main_mod.pipeline, "run_pipeline_stream", failing)

    resp = TestClient(main_mod.app).post(
        "/api/pipeline/stream", json={"topic": "新生报到", "autoRevise": False}
    )

    frames = _sse_frames(resp.text)
    assert frames[-1]["type"] == "error"
    assert "上游超时" in frames[-1]["message"]
