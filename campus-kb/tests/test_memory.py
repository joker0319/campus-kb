"""对话记忆持久化：落盘、限长、非法会话 ID 与端点契约。"""

import json

import pytest
from fastapi.testclient import TestClient

from api import deepseek, memory
from api.main import app


@pytest.fixture
def session_dir(tmp_path, monkeypatch):
    target = tmp_path / "sessions"
    monkeypatch.setenv("CAMPUS_SESSION_DIR", str(target))
    return target


class TestSessionStore:
    def test_append_then_load(self, session_dir) -> None:
        assert memory.load("s1") == []
        memory.append("s1", "上一个问题", "上一个回答")

        assert memory.load("s1") == [
            {"role": "user", "content": "上一个问题"},
            {"role": "assistant", "content": "上一个回答"},
        ]
        payload = json.loads((session_dir / "s1.json").read_text(encoding="utf-8"))
        assert payload["turns"] and payload["updatedAt"]

    def test_keeps_only_recent_turns(self, session_dir) -> None:
        for idx in range(memory.MAX_TURNS + 5):
            memory.append("s2", f"q{idx}", f"a{idx}")

        turns = memory.load("s2")
        assert len(turns) == memory.MAX_TURNS * 2
        assert turns[0]["content"] == "q5"
        assert turns[-1]["content"] == f"a{memory.MAX_TURNS + 4}"

    def test_clear_removes_session(self, session_dir) -> None:
        memory.append("s3", "问题", "回答")
        memory.clear("s3")
        assert memory.load("s3") == []
        assert not (session_dir / "s3.json").exists()

    @pytest.mark.parametrize("bad", ["../etc/passwd", "a/b", "", "x" * 65, "bad id"])
    def test_illegal_session_id_rejected(self, session_dir, bad: str) -> None:
        # 读取容错降级为空，不能让非法 ID 把问答打挂
        assert memory.load(bad) == []
        # 写入必须拒绝，杜绝路径穿越落盘
        with pytest.raises(ValueError):
            memory.append(bad, "问题", "回答")
        # clear 用于清理入口，非法 ID 直接忽略而不是抛错
        memory.clear(bad)

    def test_corrupt_file_degrades_to_empty(self, session_dir) -> None:
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "broken.json").write_text("{not json", encoding="utf-8")
        assert memory.load("broken") == []

    def test_empty_answer_is_not_persisted(self, session_dir) -> None:
        memory.append("s4", "问题", "   ")
        assert memory.load("s4") == []


class TestMemoryEndpoint:
    @pytest.fixture
    def client(self) -> TestClient:
        return TestClient(app)

    def test_stored_history_wins_and_answer_is_saved(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, session_dir
    ) -> None:
        memory.append("sess1", "上一个问题", "上一个回答")
        seen: dict[str, object] = {}

        async def fake_stream(message, rules, history=None, **kwargs):
            seen["history"] = history
            yield {
                "type": "done",
                "result": {
                    "answer": "新回答", "steps": [], "model": "test-model", "usedTools": [],
                },
            }

        monkeypatch.setattr(
            deepseek, "get_settings", lambda: deepseek.Settings(deepseek_api_key="sk-test")
        )
        monkeypatch.setattr("api.main.agent.run_agent_stream", fake_stream)

        response = client.post(
            "/api/agent/stream",
            json={
                "message": "新问题",
                "sessionId": "sess1",
                "history": [{"role": "user", "content": "前端旧历史"}],
            },
        )

        assert response.status_code == 200
        assert seen["history"] == [
            {"role": "user", "content": "上一个问题"},
            {"role": "assistant", "content": "上一个回答"},
        ]
        assert memory.load("sess1")[-1]["content"] == "新回答"

    def test_first_session_falls_back_to_request_history(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, session_dir
    ) -> None:
        seen: dict[str, object] = {}

        async def fake_stream(message, rules, history=None, **kwargs):
            seen["history"] = history
            yield {
                "type": "done",
                "result": {"answer": "回答", "steps": [], "model": "m", "usedTools": []},
            }

        monkeypatch.setattr(
            deepseek, "get_settings", lambda: deepseek.Settings(deepseek_api_key="sk-test")
        )
        monkeypatch.setattr("api.main.agent.run_agent_stream", fake_stream)

        client.post(
            "/api/agent/stream",
            json={
                "message": "新问题",
                "sessionId": "fresh",
                "history": [{"role": "user", "content": "前端历史"}, {"role": "assistant", "content": "旧回答"}],
            },
        )
        assert len(seen["history"]) == 2  # type: ignore[arg-type]

    def test_invalid_session_id_returns_422(self, client: TestClient) -> None:
        response = client.post(
            "/api/agent/stream", json={"message": "你好", "sessionId": "../bad"}
        )
        assert response.status_code == 422

    def test_clear_endpoint(self, client: TestClient, session_dir) -> None:
        memory.append("s5", "问题", "回答")
        response = client.delete("/api/agent/memory/s5")
        assert response.status_code == 200
        assert response.json() == {"ok": True}
        assert memory.load("s5") == []
