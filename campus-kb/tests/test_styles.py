"""文体模板测试：新闻 / 喜讯 / 致辞的结构路由与注入。"""

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import checker
from api import compose, deepseek, styles
from api.main import app

from test_api import _FakeAgentClient

KB = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


class TestResolveStyle:
    def test_explicit_style_wins(self) -> None:
        """显式指定优先于选题关键词——用户点「新闻」，选题里有「喜讯」也按新闻。"""
        spec = styles.resolve_style("news", "喜讯丨我校获奖")
        assert spec["id"] == "news"

    def test_auto_routes_speech(self) -> None:
        assert styles.resolve_style("auto", "写一篇奠基仪式致辞")["id"] == "speech"

    def test_auto_routes_celebration(self) -> None:
        assert styles.resolve_style("auto", "写一篇我校学者入选全球榜单的推文")["id"] == "celebration"

    def test_auto_falls_back_to_news(self) -> None:
        assert styles.resolve_style("auto", "写一篇合作大学联盟理事会会议的推文")["id"] == "news"

    def test_unknown_value_degrades_to_auto(self) -> None:
        """前端带了未知文体 id 时按 auto 处理，不 422 打断整个请求。"""
        assert styles.resolve_style("feature", "写一篇奠基仪式致辞")["id"] == "speech"

    def test_none_and_blank_treated_as_auto(self) -> None:
        assert styles.resolve_style(None, "写一篇喜讯")["id"] == "celebration"
        assert styles.resolve_style("  ", "写一篇喜讯")["id"] == "celebration"


class TestStyleBlock:
    @pytest.mark.parametrize("sid", ["news", "celebration", "speech"])
    def test_block_carries_structure_and_tone(self, sid: str) -> None:
        spec = styles.STYLES[sid]
        block = styles.style_block(spec)
        assert spec["name"] in block
        # 每套结构至少要进 prompt，否则模型还是按通用骨架写
        for item in spec["structure"]:
            assert item in block
        assert "语气" in block and "篇幅" in block

    def test_meta_marks_auto(self) -> None:
        spec = styles.STYLES["news"]
        assert styles.style_meta(spec, "auto")["auto"] is True
        assert styles.style_meta(spec, "news")["auto"] is False


class TestComposeWithStyle:
    def _run(self, style: str, topic: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[dict, list]:
        (tmp_path / "news_WX.txt").write_text("香港城市大学（东莞）举行合作大学联盟会议\n", encoding="utf-8")
        monkeypatch.setenv("CAMPUS_CORPUS_DIR", str(tmp_path))
        payload = {
            "title": "测试标题",
            "lead": "导语",
            "sections": [{"heading": "小节", "paragraphs": [{"text": "正文。", "cites": ["A1"]}]}],
            "imageSuggestions": [],
        }
        fake = _FakeAgentClient([
            {"choices": [{"message": {"role": "assistant", "content": json.dumps(payload, ensure_ascii=False)}}]}
        ])
        rules, _ = checker.load_rules()
        settings = deepseek.Settings(deepseek_api_key="sk-test", deepseek_model="test-model")
        result = asyncio.run(
            compose.compose_article(topic, rules, settings=settings, client=fake, style=style)
        )
        return result, fake.calls

    def test_speech_style_injected_into_system_prompt(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        result, calls = self._run("speech", "写一篇奠基仪式致辞", monkeypatch, tmp_path)
        system = calls[0]["json"]["messages"][0]["content"]
        assert "致辞讲稿" in system
        assert "第一人称" in system
        assert result["style"] == {"id": "speech", "name": "致辞讲稿", "auto": False}
        assert result["meta"]["style"] == "speech"

    def test_auto_celebration(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        result, calls = self._run("auto", "写一篇学者入选全球前2%榜单的推文", monkeypatch, tmp_path)
        system = calls[0]["json"]["messages"][0]["content"]
        assert "喜讯捷报" in system
        assert result["style"]["auto"] is True

    def test_news_keeps_citation_rules(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """加文体不能削弱原有约束：引用与出处规则仍要在 system 里。"""
        result, calls = self._run("news", "写一篇会议报道", monkeypatch, tmp_path)
        system = calls[0]["json"]["messages"][0]["content"]
        assert "[A1]" in system or "A1" in system
        assert result["citations"]["grounded"] is True


class TestReviseKeepsStyle:
    def test_revise_uses_given_style(self) -> None:
        """改稿带上文体，避免把致辞改成新闻腔。"""
        payload = {
            "title": "在奠基仪式上的致辞",
            "lead": "尊敬的各位领导：大家好！",
            "sections": [{"heading": "回顾", "paragraphs": [{"text": "正文。", "cites": ["A1"]}]}],
            "imageSuggestions": [],
        }
        fake = _FakeAgentClient([
            {"choices": [{"message": {"role": "assistant", "content": json.dumps(payload, ensure_ascii=False)}}]}
        ])
        rules, _ = checker.load_rules()
        settings = deepseek.Settings(deepseek_api_key="sk-test")
        blocks = [{"ref": "A1", "kind": "archive", "text": "素材", "file": "x.txt", "line": 1}]
        result = asyncio.run(
            compose.revise_article(
                "奠基仪式致辞", payload, "结尾再加一句祝愿", blocks, [], rules,
                settings=settings, client=fake, style="speech",
            )
        )
        system = fake.calls[0]["json"]["messages"][0]["content"]
        assert "致辞讲稿" in system
        assert result["style"]["id"] == "speech"
