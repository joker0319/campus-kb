"""API 契约与回归测试。

基线来自 campus-kb 实测（README「已验证的结果」）：
- bad-draft.md  命中 17 项：错误 11 / 警告 6
- good-draft.md 命中 0 项
任何改动导致这两个数字变化，必须先确认是规则更新所致并同步 README。
"""

import asyncio
import json
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import agent, deepseek
from api.main import app
from api.search import load_corpus, search

KB = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def _sample(name: str) -> str:
    return (KB / "samples" / f"{name}.md").read_text(encoding="utf-8")


class TestHealth:
    def test_ok(self, client: TestClient) -> None:
        assert client.get("/api/health").json() == {"status": "ok"}


class TestRules:
    def test_19_rules(self, client: TestClient) -> None:
        r = client.get("/api/rules")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 19
        assert len(data["rules"]) == 19

    def test_every_rule_has_source(self, client: TestClient) -> None:
        for rule in client.get("/api/rules").json()["rules"]:
            assert rule["source"], f"{rule['id']} 缺出处"
            assert rule["file"], f"{rule['id']} 缺文件名"


class TestReview:
    def test_bad_draft_baseline(self, client: TestClient) -> None:
        r = client.post("/api/review", json={"content": _sample("bad-draft")})
        assert r.status_code == 200
        data = r.json()
        assert data["counts"] == {"total": 17, "error": 11, "warn": 6, "info": 0}
        assert data["ruleCount"] == 19

    def test_good_draft_zero_finding(self, client: TestClient) -> None:
        r = client.post("/api/review", json={"content": _sample("good-draft")})
        assert r.status_code == 200
        data = r.json()
        assert data["counts"]["total"] == 0
        assert data["findings"] == []

    def test_findings_sorted_by_line(self, client: TestClient) -> None:
        lines = [f["line"] for f in
                 client.post("/api/review", json={"content": _sample("bad-draft")}).json()["findings"]]
        assert lines == sorted(lines)

    def test_keys_stable_and_unique(self, client: TestClient) -> None:
        findings = client.post("/api/review",
                               json={"content": _sample("bad-draft")}).json()["findings"]
        keys = [f["key"] for f in findings]
        assert len(keys) == len(set(keys)), "key 冲突会导致前端忽略/回链串行"
        for f in findings:
            assert f["key"].startswith(f"{f['ruleId']}@{f['line']}")

    def test_same_line_multiple_hits_get_suffix(self, client: TestClient) -> None:
        # 一行里踩两条 PUNCT-003 词对：第二个命中必须拿到 -2 后缀而不是覆盖
        text = "他出生于1978/5/1，入学时间是2019/9/3。\n"
        findings = client.post("/api/review", json={"content": text}).json()["findings"]
        dates = [f for f in findings if f["ruleId"].startswith("PUNCT")]
        if len(dates) >= 2:
            assert dates[0]["key"] != dates[1]["key"]

    def test_empty_content_rejected(self, client: TestClient) -> None:
        assert client.post("/api/review", json={"content": ""}).status_code == 422

    def test_layout_config_not_in_findings(self, client: TestClient) -> None:
        # layout.json 是排版配置（0 条规则），不该出现在校验结果里
        ids = {f["ruleId"] for f in
               client.post("/api/review", json={"content": _sample("bad-draft")}).json()["findings"]}
        assert ids and all(not i.startswith("LAYOUT") for i in ids)


class TestHitField:
    """每条命中都带精确原文子串，前端据此给任意稿件标红。"""

    def test_every_finding_has_hit_in_source(self) -> None:
        from checker import load_rules, run

        text = _sample("bad-draft")
        rules, _ = load_rules()
        findings = run(text, rules)
        assert findings
        for f in findings:
            assert f["hit"], f"{f['rule_id']} 缺 hit"
            assert f["hit"] in text, f"{f['rule_id']} 的 hit 不是原文子串"

    def test_api_returns_hit(self, client: TestClient) -> None:
        findings = client.post(
            "/api/review", json={"content": _sample("bad-draft")}
        ).json()["findings"]
        assert all(f["hit"] for f in findings)


class TestModes:
    """mode=submission（默认）全量规则；archive 跳过投稿格式规则（SUB-*）。"""

    def test_default_mode_is_submission(self, client: TestClient) -> None:
        r = client.post("/api/review", json={"content": _sample("bad-draft")})
        assert r.json()["ruleCount"] == 19

    def test_archive_mode_skips_sub_rules(self, client: TestClient) -> None:
        r = client.post("/api/review",
                        json={"content": _sample("bad-draft"), "mode": "archive"})
        data = r.json()
        assert all(not f["ruleId"].startswith("SUB") for f in data["findings"])
        assert data["ruleCount"] == 15

    def test_archive_mode_keeps_content_rules(self, client: TestClient) -> None:
        ids = {f["ruleId"] for f in client.post(
            "/api/review", json={"content": _sample("bad-draft"), "mode": "archive"}
        ).json()["findings"]}
        assert "NAME-001" in ids and "PUNCT-003" in ids

    def test_invalid_mode_rejected(self, client: TestClient) -> None:
        r = client.post("/api/review",
                        json={"content": "测试内容", "mode": "chat"})
        assert r.status_code == 422


class TestPunctExemptions:
    """数字间的冒号/逗号是时间/比值/千分位，不是半角标点错误。"""

    @pytest.mark.parametrize("text", [
        "会议时间是明天上午22:00，届时请准时参加\n",
        "预计在校生规模比例约为1:1，研究生占四成\n",
        "本次投入经费约1,000万元，用于设备采购\n",
    ])
    def test_digit_punct_exempt(self, client: TestClient, text: str) -> None:
        findings = client.post("/api/review", json={"content": text}).json()["findings"]
        assert not any(f["ruleId"] == "PUNCT-001" for f in findings), text

    def test_real_halfwidth_comma_still_caught(self, client: TestClient) -> None:
        findings = client.post(
            "/api/review", json={"content": "他表示,学校将持续推动合作\n"}
        ).json()["findings"]
        assert any(f["ruleId"] == "PUNCT-001" for f in findings)


@pytest.fixture()
def corpus_root(tmp_path: Path) -> Path:
    """注入临时语料目录。缓存 key 为「路径 + 版本戳」，不同临时目录互不干扰。"""
    (tmp_path / "a.txt").write_text(
        "第一行没有关键词\n于吉红院士出席了奠基仪式\n又是无关行，奠基仪式很隆重\n",
        encoding="utf-8",
    )
    (tmp_path / "b.txt").write_text("奠基仪式于四月举行\n", encoding="utf-8")
    yield tmp_path


class TestSearch:
    def test_single_term(self, corpus_root: Path) -> None:
        r = search("奠基", root=corpus_root)
        assert r["total"] == 3
        assert r["scanned"] == 2
        assert r["results"][0]["file"] == "a"  # a 命中 2 行排前，name 为 stem

    def test_multi_term_is_and(self, corpus_root: Path) -> None:
        r = search("于吉红 奠基", root=corpus_root)
        assert r["total"] == 1
        assert r["results"][0]["line"] == 2

    def test_case_insensitive(self, corpus_root: Path) -> None:
        (corpus_root / "c.txt").write_text("CityU(DG) held a ceremony\n", encoding="utf-8")
        r = search("cityu", root=corpus_root)
        assert r["total"] == 1

    def test_no_match(self, corpus_root: Path) -> None:
        r = search("不存在的词", root=corpus_root)
        assert r["total"] == 0 and r["results"] == []

    def test_empty_query(self, corpus_root: Path) -> None:
        assert search("   ", root=corpus_root)["total"] == 0

    def test_语料变更后无需重启即可检索(self, tmp_path: Path) -> None:
        """抓完新文章应当立刻能搜到：缓存 key 带文件版本戳，不能是纯路径缓存。"""
        import time

        target = tmp_path / "wx.txt"
        target.write_text("初始内容\n", encoding="utf-8")
        assert search("初始内容", root=tmp_path)["total"] == 1

        time.sleep(0.01)  # 保证 mtime_ns 变化
        target.write_text("初始内容\n新增的公众号段落\n", encoding="utf-8")
        assert search("新增的公众号段落", root=tmp_path)["total"] == 1

    def test_endpoint(self, client: TestClient, corpus_root: Path) -> None:
        # 端点走默认语料目录，用 monkeypatch 指向临时目录
        import api.main as m
        orig = m.corpus_search.corpus_dir
        m.corpus_search.corpus_dir = lambda: corpus_root  # type: ignore[assignment]
        try:
            r = client.get("/api/search", params={"q": "奠基"})
            assert r.status_code == 200
            assert r.json()["total"] == 3
        finally:
            m.corpus_search.corpus_dir = orig  # type: ignore[assignment]

    def test_endpoint_requires_q(self, client: TestClient) -> None:
        assert client.get("/api/search").status_code == 422


def _docx_bytes(text: str) -> bytes:
    """在内存生成一个 docx，每行一个段落。"""
    from io import BytesIO
    from docx import Document

    doc = Document()
    for line in text.split("\n"):
        doc.add_paragraph(line)
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


class TestReviewFile:
    def test_upload_docx_returns_baseline_findings(self, client: TestClient) -> None:
        text = Path("samples/bad-draft.md").read_text(encoding="utf-8")
        r = client.post(
            "/api/review-file",
            files={"file": ("bad-draft.docx", _docx_bytes(text),
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["filename"] == "bad-draft.docx"
        assert data["counts"]["total"] == 17
        assert data["counts"]["error"] == 11
        assert data["ruleCount"] == 19
        assert "香港城市大学" in data["text"]

    def test_report_contains_sources_and_findings(self, client: TestClient) -> None:
        text = Path("samples/bad-draft.md").read_text(encoding="utf-8")
        r = client.post("/api/review-file", files={"file": ("bad.docx", _docx_bytes(text))})
        report = r.json()["report"]
        assert "# 稿件校验报告" in report
        assert "## 问题清单" in report
        assert "## 覆盖的规范来源" in report
        assert "PUNCT-001" in report

    def test_rejects_non_docx(self, client: TestClient) -> None:
        r = client.post("/api/review-file", files={"file": ("note.txt", b"hello")})
        assert r.status_code == 400
        assert ".docx" in r.json()["detail"]

    def test_rejects_corrupt_docx(self, client: TestClient) -> None:
        r = client.post("/api/review-file", files={"file": ("broken.docx", b"not a real docx")})
        assert r.status_code == 400


class TestChat:
    """AI 问答：密钥缺失明确报错；上下文来自检索；端点契约稳定。"""

    def test_without_key_returns_503_with_clear_message(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            deepseek, "get_settings", lambda: deepseek.Settings(deepseek_api_key="")
        )
        r = client.post("/api/chat", json={"message": "校名有什么规范？"})
        assert r.status_code == 503
        assert "DEEPSEEK_API_KEY" in r.json()["detail"]

    def test_empty_message_rejected(self, client: TestClient) -> None:
        assert client.post("/api/chat", json={"message": ""}).status_code == 422

    def test_build_context_picks_rules_and_archives(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import checker

        rules, _ = checker.load_rules()
        context, sources = deepseek.build_context("校名首次出现要用全称吗？", rules)
        assert "[S1]" in context
        assert any(s["kind"] == "rule" for s in sources)
        assert any(s["kind"] == "archive" for s in sources)
        assert all(s["ref"] for s in sources)

    def test_ask_builds_prompt_and_parses_response(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import checker

        settings = deepseek.Settings(deepseek_api_key="sk-test", deepseek_model="test-model")
        captured: dict = {}

        class FakeResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {"choices": [{"message": {"content": "根据 [S1]，首次用全称。"}}]}

        class FakeClient:
            def __init__(self, **_kwargs: object) -> None:
                return None

            async def __aenter__(self) -> "FakeClient":
                return self

            async def __aexit__(self, *_args: object) -> bool:
                return False

            async def post(self, url: str, **kwargs: object) -> FakeResponse:
                captured["url"] = url
                captured["kwargs"] = kwargs
                return FakeResponse()

        monkeypatch.setattr(deepseek.httpx, "AsyncClient", FakeClient)
        rules, _ = checker.load_rules()
        result = asyncio.run(deepseek.ask("校名首次出现要用全称吗？", rules, settings=settings))

        assert captured["url"] == "https://api.deepseek.com/chat/completions"
        kwargs = captured["kwargs"]
        assert kwargs["json"]["model"] == "test-model"
        messages = kwargs["json"]["messages"]
        assert messages[0]["role"] == "system"
        assert "[S1]" in messages[0]["content"]
        assert messages[-1]["role"] == "user"
        assert result["answer"] == "根据 [S1]，首次用全称。"
        assert result["sources"]
        assert result["model"] == "test-model"

    def test_chat_endpoint_returns_answer_and_sources(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def fake_ask(question: str, rules: list[dict], history=None, settings=None) -> dict:
            return {
                "answer": "首次出现请用全称。",
                "sources": [
                    {"ref": "S1", "kind": "rule", "title": "NAME-001", "detail": "校名用全称"}
                ],
                "model": "deepseek-chat",
            }

        monkeypatch.setattr(deepseek, "ask", fake_ask)
        r = client.post("/api/chat", json={"message": "校名规范？", "history": []})
        assert r.status_code == 200
        data = r.json()
        assert data["answer"] == "首次出现请用全称。"
        assert data["sources"][0]["ref"] == "S1"
        assert data["model"] == "deepseek-chat"


class TestAgent:
    """Agent：模型自选工具 → 本地确定性执行 → 回灌 → 回答。用假 client 模拟多轮，不依赖网络。"""

    def test_without_key_returns_503(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            deepseek, "get_settings", lambda: deepseek.Settings(deepseek_api_key="")
        )
        r = client.post("/api/agent", json={"message": "查一下标点规范"})
        assert r.status_code == 503
        assert "DEEPSEEK_API_KEY" in r.json()["detail"]

    def test_empty_message_rejected(self, client: TestClient) -> None:
        assert client.post("/api/agent", json={"message": ""}).status_code == 422

    def test_direct_answer_without_tools(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """模型不需要工具时直接回答，steps 为空。"""
        import checker

        settings = deepseek.Settings(deepseek_api_key="sk-test", deepseek_model="test-model")
        responses = [
            {"choices": [{"message": {"role": "assistant", "content": "你好，我是知识库助手。"}}]}
        ]
        fake = _FakeAgentClient(responses)
        rules, _ = checker.load_rules()
        result = asyncio.run(agent.run_agent("你好", rules, settings=settings, client=fake))

        assert result["answer"] == "你好，我是知识库助手。"
        assert result["steps"] == []
        assert result["usedTools"] == []
        assert len(fake.calls) == 1
        assert fake.calls[0]["json"]["tool_choice"] == "auto"
        assert any(t["function"]["name"] == "search_rules" for t in fake.calls[0]["json"]["tools"])

    def test_tool_call_search_rules_returns_structured_steps(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """模型调 search_rules → 本地检索 → 回灌 → 生成答案，轨迹可被前端展示。"""
        import checker

        settings = deepseek.Settings(deepseek_api_key="sk-test", deepseek_model="test-model")
        responses = [
            {
                "choices": [{
                    "message": {
                        "role": "assistant", "content": "",
                        "tool_calls": [{
                            "id": "call_1", "type": "function",
                            "function": {"name": "search_rules", "arguments": '{"keyword":"标点"}'},
                        }],
                    }
                }]
            },
            {"choices": [{"message": {"role": "assistant", "content": "中文应用全角标点。"}}]},
        ]
        fake = _FakeAgentClient(responses)
        rules, _ = checker.load_rules()
        result = asyncio.run(agent.run_agent("标点有什么规范？", rules, settings=settings, client=fake))

        assert result["answer"] == "中文应用全角标点。"
        assert result["usedTools"] == ["search_rules"]
        assert result["steps"][0]["tool"] == "search_rules"
        assert result["steps"][0]["args"] == {"keyword": "标点"}
        assert result["steps"][0]["result"]["kind"] == "rules"
        assert result["steps"][0]["result"]["items"]  # 本地确实查到了规则
        # 第二轮消息里应含 tool 回灌
        second = fake.calls[1]["json"]["messages"]
        assert any(m.get("role") == "tool" and m.get("tool_call_id") == "call_1" for m in second)

    def test_review_tool_uses_rule_engine_result(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """校验结论来自规则引擎，不来自模型编造。"""
        import checker

        settings = deepseek.Settings(deepseek_api_key="sk-test", deepseek_model="test-model")
        responses = [
            {
                "choices": [{
                    "message": {
                        "role": "assistant", "content": "",
                        "tool_calls": [{
                            "id": "call_r", "type": "function",
                            "function": {
                                "name": "review_draft",
                                "arguments": json.dumps({"content": "港城大（东莞）在2027年QS排名位列第63位。"}),
                            },
                        }],
                    }
                }]
            },
            {"choices": [{"message": {"role": "assistant", "content": "发现规范问题，见下方结果。"}}]},
        ]
        fake = _FakeAgentClient(responses)
        rules, _ = checker.load_rules()
        result = asyncio.run(agent.run_agent("帮我检查这段稿件", rules, settings=settings, client=fake))

        review = result["steps"][0]["result"]
        assert review["kind"] == "review"
        assert review["counts"]["total"] >= 1
        assert all(item["ruleId"] for item in review["items"])
        # 回灌给模型的文本含真实命中，而非模型自由发挥
        tool_msg = next(
            m for m in fake.calls[1]["json"]["messages"] if m.get("role") == "tool"
        )
        assert "规则引擎校验完成" in tool_msg["content"]

    def test_step_limit_returns_truncated_not_hang(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """模型一直调工具不收敛时，达到上限明确收尾，不无限循环。"""
        import checker

        settings = deepseek.Settings(deepseek_api_key="sk-test", deepseek_model="test-model")

        def always_tool(_req: dict) -> dict:
            return {
                "choices": [{
                    "message": {
                        "role": "assistant", "content": "",
                        "tool_calls": [{
                            "id": "call_x", "type": "function",
                            "function": {"name": "search_archive", "arguments": '{"query":"奠基"}'},
                        }],
                    }
                }]
            }

        fake = _FakeAgentClient(responder=always_tool)
        rules, _ = checker.load_rules()
        result = asyncio.run(agent.run_agent("一直查档案", rules, settings=settings, client=fake))

        assert result["truncated"] is True
        assert len(fake.calls) == agent.MAX_STEPS
        assert "工具调用达到上限" in result["answer"]

    def test_endpoint_contract(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        """POST /api/agent 返回 answer / steps / usedTools / model。"""
        import checker

        settings = deepseek.Settings(deepseek_api_key="sk-test", deepseek_model="test-model")
        responses = [
            {"choices": [{"message": {"role": "assistant", "content": "已查询。"}}]}
        ]
        fake = _FakeAgentClient(responses)
        monkeypatch.setattr(deepseek, "get_settings", lambda: settings)
        monkeypatch.setattr(agent.httpx, "AsyncClient", lambda **_kw: fake)
        rules, _ = checker.load_rules()
        monkeypatch.setattr("api.main.get_engine", lambda: (rules, []))

        r = client.post("/api/agent", json={"message": "校训是什么？"})
        assert r.status_code == 200
        data = r.json()
        assert data["answer"] == "已查询。"
        assert data["steps"] == []
        assert data["usedTools"] == []
        assert data["model"] == "test-model"


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeAgentClient:
    """按序返回预设响应，或用 responder 动态生成；记录每次请求的 json body。"""

    def __init__(
        self,
        responses: list[dict] | None = None,
        responder: "Callable[[dict], dict] | None" = None,
    ) -> None:
        self._responses = list(responses or [])
        self._responder = responder
        self.calls: list[dict] = []

    async def __aenter__(self) -> "_FakeAgentClient":
        return self

    async def __aexit__(self, *_args: object) -> bool:
        return False

    async def aclose(self) -> None:
        return None

    async def post(self, url: str, **kwargs: object) -> _FakeResponse:
        self.calls.append({"url": url, "json": kwargs["json"]})
        if self._responder:
            return _FakeResponse(self._responder(kwargs["json"]))
        idx = len(self.calls) - 1
        return _FakeResponse(self._responses[min(idx, len(self._responses) - 1)])
