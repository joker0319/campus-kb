"""流式成稿：SSE 解析、事件序列与错误帧。"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api import compose, deepseek, main as main_mod
from api.deepseek import Settings

SSE_LINES = [
    'data: {"choices":[{"delta":{"content":"{\\"title\\":\\"报到指引\\","}}]}',
    ": keep-alive",
    "data: not-json",
    'data: {"choices":[{"delta":{"content":"\\"lead\\":\\"导语\\"}"}}]}',
    'data: {"choices":[]}',
    "data: [DONE]",
]


class _FakeResponse:
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    def raise_for_status(self) -> None:
        return None

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeStream:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    async def __aenter__(self) -> _FakeResponse:
        return self._response

    async def __aexit__(self, *exc: object) -> bool:
        return False


class _FakeClient:
    """只实现 stream()，够 _stream_model_raw 用。"""

    def __init__(self, lines: list[str]) -> None:
        self.lines = lines
        self.calls: list[dict[str, Any]] = []

    def stream(self, method: str, url: str, **kwargs: Any) -> _FakeStream:
        self.calls.append({"method": method, "url": url, **kwargs})
        return _FakeStream(_FakeResponse(self.lines))


def test_stream_model_raw_parses_sse_and_skips_noise() -> None:
    cfg = Settings(deepseek_api_key="test-key")
    client = _FakeClient(SSE_LINES)

    async def collect() -> list[str]:
        return [t async for t in compose._stream_model_raw(cfg, "sys", "user", client)]  # type: ignore[arg-type]

    chunks = asyncio.run(collect())

    assert "".join(chunks) == '{"title":"报到指引","lead":"导语"}'
    body = client.calls[0]["json"]
    assert body["stream"] is True
    # JSON 模式不能丢，否则结构化输出会退化
    assert body["response_format"] == {"type": "json_object"}


class _FakeCtx(dict):
    pass


def _fake_ctx(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = {
        "cfg": Settings(deepseek_api_key="test-key"),
        "spec": {"id": "news", "name": "新闻动态"},
        "blocks": [],
        "rule_items": [],
        "meta": {"terms": [], "scanned": 0, "style": "news"},
        "user_prompt": "u",
        "system_prompt": "s",
    }
    monkeypatch.setattr(compose, "_prepare", lambda *a, **k: ctx)


def test_stream_emits_meta_deltas_then_done(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_ctx(monkeypatch)

    async def fake_raw(*a: Any, **k: Any):
        for piece in ('{"title":"报到指引",', '"sections":[{"heading":"一","paragraphs":[{"text":"正文。","cites":["A1"]}]}]}'):
            yield piece

    monkeypatch.setattr(compose, "_stream_model_raw", fake_raw)

    async def collect() -> list[dict]:
        return [e async for e in compose.compose_article_stream("报到", [])]

    events = asyncio.run(collect())

    assert events[0]["type"] == "meta"
    assert events[0]["style"]["id"] == "news"
    assert [e["type"] for e in events[1:-1]] == ["delta", "delta"]
    done = events[-1]
    assert done["type"] == "done"
    assert done["result"]["article"]["title"] == "报到指引"
    assert done["result"]["markdown"]
    assert done["result"]["html"]


def test_stream_rejects_incomplete_output(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_ctx(monkeypatch)

    async def fake_raw(*a: Any, **k: Any):
        yield '{"title":"只有标题"'

    monkeypatch.setattr(compose, "_stream_model_raw", fake_raw)

    async def collect() -> list[dict]:
        return [e async for e in compose.compose_article_stream("报到", [])]

    with pytest.raises(deepseek.DeepSeekUnavailable):
        asyncio.run(collect())


def _sse_frames(text: str) -> list[dict]:
    frames = []
    for block in text.split("\n\n"):
        line = next((ln for ln in block.splitlines() if ln.startswith("data:")), None)
        if line:
            frames.append(json.loads(line[5:].strip()))
    return frames


def test_stream_endpoint_serializes_events(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(deepseek, "get_settings", lambda: Settings(deepseek_api_key="test-key"))

    async def fake_stream(*a: Any, **k: Any):
        yield {"type": "meta", "style": {"id": "news", "name": "新闻动态", "auto": True}}
        yield {"type": "delta", "text": '{"title":"报到"'}
        yield {"type": "done", "result": {"article": {"title": "报到"}}}

    monkeypatch.setattr(main_mod, "compose_article_stream", fake_stream)

    resp = TestClient(main_mod.app).post("/api/compose/stream", json={"topic": "新生报到"})

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert resp.headers["x-accel-buffering"] == "no"
    types = [f["type"] for f in _sse_frames(resp.text)]
    assert types == ["meta", "delta", "done"]


def test_stream_endpoint_returns_503_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(deepseek, "get_settings", lambda: Settings(deepseek_api_key=""))

    resp = TestClient(main_mod.app).post("/api/compose/stream", json={"topic": "新生报到"})

    assert resp.status_code == 503


def test_stream_endpoint_sends_error_event(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(deepseek, "get_settings", lambda: Settings(deepseek_api_key="test-key"))

    async def failing(*a: Any, **k: Any):
        yield {"type": "meta", "style": {"id": "news", "name": "新闻动态", "auto": True}}
        raise deepseek.DeepSeekUnavailable("上游超时")

    monkeypatch.setattr(main_mod, "compose_article_stream", failing)

    resp = TestClient(main_mod.app).post("/api/compose/stream", json={"topic": "新生报到"})

    frames = _sse_frames(resp.text)
    assert frames[-1]["type"] == "error"
    assert "上游超时" in frames[-1]["message"]
