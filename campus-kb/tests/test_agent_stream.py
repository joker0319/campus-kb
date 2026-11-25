"""Agent 流式问答回归：SSE 事件序列、分片 tool_calls 合并、端点契约。

不依赖网络：用假 httpx client 按轮返回预设的 SSE 文本行。
"""

import asyncio
import json
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient

import checker
from api import agent, deepseek
from api.main import app


def _chunk(delta: dict) -> str:
    return "data: " + json.dumps({"choices": [{"delta": delta}]}, ensure_ascii=False)


def _text_round(*parts: str) -> list[str]:
    return [_chunk({"content": p}) for p in parts] + ["data: [DONE]"]


def _tool_round(name: str, args: dict, call_id: str = "call_1") -> list[str]:
    """把工具调用刻意切成三片，验证按 index 合并而非取最后一帧。"""
    raw = json.dumps(args, ensure_ascii=False)
    cut = max(1, len(raw) // 3)
    name_a, name_b = name[:3], name[3:]
    return [
        _chunk({
            "tool_calls": [{
                "index": 0, "id": call_id, "type": "function",
                "function": {"name": name_a, "arguments": ""},
            }]
        }),
        _chunk({
            "tool_calls": [{
                "index": 0,
                "function": {"name": name_b, "arguments": raw[:cut]},
            }]
        }),
        _chunk({
            "tool_calls": [{
                "index": 0,
                "function": {"arguments": raw[cut:]},
            }]
        }),
        "data: [DONE]",
    ]


class _FakeStreamResponse:
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    def raise_for_status(self) -> None:
        return None

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeStreamClient:
    """支持 async with client.stream(...)，按轮返回预设 SSE 行。"""

    def __init__(self, rounds: list[list[str]]) -> None:
        self._rounds = rounds
        self.calls: list[dict] = []

    @asynccontextmanager
    async def stream(self, method: str, url: str, **kwargs: object):
        self.calls.append({"method": method, "url": url, "json": kwargs["json"]})
        idx = len(self.calls) - 1
        yield _FakeStreamResponse(self._rounds[min(idx, len(self._rounds) - 1)])

    async def aclose(self) -> None:
        return None


def _settings() -> deepseek.Settings:
    return deepseek.Settings(deepseek_api_key="sk-test", deepseek_model="test-model")


async def _collect(gen) -> list[dict]:
    return [event async for event in gen]


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


class TestRunAgentStream:
    def test_direct_answer_emits_meta_delta_then_done(self) -> None:
        fake = _FakeStreamClient([_text_round("你好，", "我是", "知识库助手。")])
        rules, _ = checker.load_rules()

        events = asyncio.run(_collect(
            agent.run_agent_stream("你好", rules, settings=_settings(), client=fake)
        ))

        assert [e["type"] for e in events] == [
            "meta", "delta", "delta", "delta", "done",
        ]
        assert events[0]["model"] == "test-model"
        assert "".join(e["text"] for e in events if e["type"] == "delta") == "你好，我是知识库助手。"
        done = events[-1]["result"]
        assert done["answer"] == "你好，我是知识库助手。"
        assert done["steps"] == []
        assert done["usedTools"] == []
        assert fake.calls[0]["json"]["stream"] is True

    def test_step_is_emitted_before_answer_deltas(self) -> None:
        fake = _FakeStreamClient([
            _tool_round("search_rules", {"keyword": "标点"}),
            _text_round("中文应用", "全角标点。"),
        ])
        rules, _ = checker.load_rules()

        events = asyncio.run(_collect(
            agent.run_agent_stream("标点规范？", rules, settings=_settings(), client=fake)
        ))

        kinds = [e["type"] for e in events]
        assert kinds == ["meta", "step", "delta", "delta", "done"]
        step = events[1]["step"]
        assert step["tool"] == "search_rules"
        # 跨三片拼起来的 name / arguments 必须完整
        assert step["args"] == {"keyword": "标点"}
        assert step["result"]["kind"] == "rules"
        assert step["result"]["items"]
        assert events[-1]["result"]["answer"] == "中文应用全角标点。"
        assert events[-1]["result"]["usedTools"] == ["search_rules"]
        # 第二轮回灌里带工具结果，模型不是凭记忆作答
        messages = fake.calls[1]["json"]["messages"]
        assert any(m.get("role") == "tool" and m.get("tool_call_id") == "call_1" for m in messages)

    def test_step_limit_marks_truncated(self) -> None:
        # 每轮都调工具，永远不收敛
        fake = _FakeStreamClient([_tool_round("search_rules", {"keyword": "档案"})])
        rules, _ = checker.load_rules()

        events = asyncio.run(_collect(
            agent.run_agent_stream("一直查", rules, settings=_settings(), client=fake)
        ))

        assert len([e for e in events if e["type"] == "step"]) == agent.MAX_STEPS
        final = next(e for e in events if e["type"] == "done")["result"]
        assert final["truncated"] is True
        assert "工具调用达到上限" in final["answer"]

    def test_blank_key_raises_before_any_frame(self) -> None:
        rules, _ = checker.load_rules()
        settings = deepseek.Settings(deepseek_api_key="")
        with pytest.raises(deepseek.DeepSeekNotConfigured):
            asyncio.run(_collect(agent.run_agent_stream("你好", rules, settings=settings)))


class TestAgentStreamEndpoint:
    def test_sse_frames_match_done_result(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        async def fake_stream(*_args: object, **_kwargs: object):
            yield {"type": "meta", "model": "test-model"}
            yield {"type": "delta", "text": "来自"}
            yield {"type": "delta", "text": "流式。"}
            yield {
                "type": "done",
                "result": {
                    "answer": "来自流式。", "steps": [], "model": "test-model", "usedTools": [],
                },
            }

        monkeypatch.setattr(deepseek, "get_settings", lambda: _settings())
        monkeypatch.setattr(agent, "run_agent_stream", fake_stream)

        r = client.post("/api/agent/stream", json={"message": "你好", "history": []})
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        assert r.headers["x-accel-buffering"] == "no"
        frames = [
            json.loads(line[5:])
            for line in r.text.splitlines()
            if line.startswith("data: ")
        ]
        assert [f["type"] for f in frames] == ["meta", "delta", "delta", "done"]
        assert frames[-1]["result"]["answer"] == "来自流式。"

    def test_upstream_failure_becomes_error_event(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_stream(*_args: object, **_kwargs: object):
            yield {"type": "meta", "model": "test-model"}
            raise deepseek.DeepSeekUnavailable("上游不可用")

        monkeypatch.setattr(deepseek, "get_settings", lambda: _settings())
        monkeypatch.setattr(agent, "run_agent_stream", fake_stream)

        r = client.post("/api/agent/stream", json={"message": "你好"})
        assert r.status_code == 200  # 响应已开始，不能改状态码
        frames = [
            json.loads(line[5:])
            for line in r.text.splitlines()
            if line.startswith("data: ")
        ]
        assert frames[-1]["type"] == "error"
        assert "上游不可用" in frames[-1]["message"]

    def test_blank_key_returns_503(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            deepseek, "get_settings", lambda: deepseek.Settings(deepseek_api_key="")
        )
        r = client.post("/api/agent/stream", json={"message": "你好"})
        assert r.status_code == 503
        assert "DEEPSEEK_API_KEY" in r.json()["detail"]
