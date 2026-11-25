"""文章生成测试：检索 → 成稿 → 出处/规范校验。用假 client，不依赖网络与密钥。"""

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import checker
from api import compose, deepseek
from api.main import app

from test_api import _FakeAgentClient

KB = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def _article_payload() -> dict:
    """模型返回的合规 JSON：所有段落都带真实素材编号 A1。"""
    return {
        "title": "港城莞科研新进展",
        "lead": "一句话导语",
        "sections": [
            {
                "heading": "科研",
                "paragraphs": [
                    {"text": "据档案记载，学校取得进展。", "cites": ["A1"]},
                ],
            }
        ],
        "imageSuggestions": [{"after": "科研", "description": "实验室照片"}],
    }


class TestGatherMaterial:
    def test_returns_numbered_blocks(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """检索结果带 A# 编号、文件名与行号；规范带 R# 编号。"""
        (tmp_path / "x_WX.txt").write_text("学校取得重要科研进展\n", encoding="utf-8")
        monkeypatch.setenv("CAMPUS_CORPUS_DIR", str(tmp_path))
        rules, _ = checker.load_rules()
        blocks, rule_items, meta = compose.gather_material("科研进展", rules)

        assert blocks
        assert blocks[0]["ref"].startswith("A")
        assert blocks[0]["file"].endswith("_WX.txt")
        assert "line" in blocks[0] and "text" in blocks[0]
        assert meta["scanned"] >= 1

    def test_empty_corpus_returns_no_blocks(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("CAMPUS_CORPUS_DIR", str(tmp_path))
        rules, _ = checker.load_rules()
        blocks, _, _ = compose.gather_material("不存在的话题", rules)
        assert blocks == []

    def test_uses_full_chunk_not_short_excerpt(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """关键事实在 96 字之外时，成稿素材必须带完整块，不能只给摘要。"""
        text = (
            "学校概况与办学理念介绍部分很长很长，反复说明校园位于松山湖科学城，"
            "坚持教研合一与两校一质，本科生从入学起就有机会进入实验室参与科研。"
            "关键事实：2027年QS世界大学排名位列第52位。"
        )
        (tmp_path / "x_WX.txt").write_text(text + "\n", encoding="utf-8")
        monkeypatch.setenv("CAMPUS_CORPUS_DIR", str(tmp_path))
        monkeypatch.setenv("CAMPUS_EMBEDDING", "off")
        rules, _ = checker.load_rules()
        blocks, _, _ = compose.gather_material("学校QS排名", rules)

        assert blocks
        assert any("第52位" in b["text"] for b in blocks)


class TestParseArticle:
    def test_parses_valid_json(self) -> None:
        article = compose.parse_article(json.dumps(_article_payload(), ensure_ascii=False))
        assert article["title"] == "港城莞科研新进展"
        assert article["sections"][0]["paragraphs"][0]["cites"] == ["A1"]
        assert article["imageSuggestions"][0]["description"] == "实验室照片"

    def test_strips_code_fence(self) -> None:
        raw = "```json\n" + json.dumps(_article_payload(), ensure_ascii=False) + "\n```"
        assert compose.parse_article(raw)["title"] == "港城莞科研新进展"

    def test_invalid_json_degrades_to_empty(self) -> None:
        article = compose.parse_article("not json")
        assert article["title"] == ""
        assert article["sections"] == []

    def test_drops_truncated_sentences(self) -> None:
        """被切断的素材句不能流到发布稿里，宁可整句丢掉。"""
        payload = _article_payload()
        payload["sections"][0]["paragraphs"][0]["text"] = (
            "学校录取最低分为62…（素材原文截断，具体分数待补充）。完整事实在此。"
        )
        text = compose.parse_article(json.dumps(payload, ensure_ascii=False))[
            "sections"
        ][0]["paragraphs"][0]["text"]
        assert "素材原文截断" not in text
        assert "…" not in text
        assert "完整事实在此。" in text

    def test_inline_cites_move_out_of_text(self) -> None:
        """模型把 [A1] 写进正文时，正文要干净、编号并回 cites，前端只渲染一次角标。"""
        payload = _article_payload()
        payload["sections"][0]["paragraphs"] = [
            {"text": "据档案记载，学校取得进展。[A1][A2]", "cites": ["A1"]},
        ]
        article = compose.parse_article(json.dumps(payload, ensure_ascii=False))
        para = article["sections"][0]["paragraphs"][0]
        assert "[A1]" not in para["text"] and "[A2]" not in para["text"]
        assert para["text"] == "据档案记载，学校取得进展。"
        # 正文明写的编号并回 cites，且与显式给的编号去重
        assert para["cites"] == ["A1", "A2"]

    def test_inline_cites_stripped_from_title_and_lead(self) -> None:
        payload = _article_payload()
        payload["title"] = "港城莞科研新进展 [A1]"
        payload["lead"] = "一句话导语[A2]"
        article = compose.parse_article(json.dumps(payload, ensure_ascii=False))
        assert article["title"] == "港城莞科研新进展"
        assert article["lead"] == "一句话导语"

    def test_fullwidth_brackets_also_stripped(self) -> None:
        payload = _article_payload()
        payload["sections"][0]["paragraphs"] = [{"text": "正文内容【A1】", "cites": []}]
        para = compose.parse_article(json.dumps(payload, ensure_ascii=False))["sections"][0][
            "paragraphs"
        ][0]
        assert para["text"] == "正文内容【A1】"  # 中文方头括号是正常正文，不改动
        assert para["cites"] == []


class TestCheckCitations:
    def test_grounded_when_all_paragraphs_cited(self) -> None:
        blocks = [{"ref": "A1", "file": "x.txt", "line": 1, "text": "", "kind": "archive"}]
        article = compose.parse_article(json.dumps(_article_payload(), ensure_ascii=False))
        report = compose.check_citations(article, blocks)
        assert report["grounded"] is True
        assert report["uncitedParagraphs"] == 0
        assert [s["ref"] for s in report["cited"]] == ["A1"]

    def test_uncited_paragraph_flagged(self) -> None:
        blocks = [{"ref": "A1", "file": "x.txt", "line": 1, "text": "", "kind": "archive"}]
        article = {
            "sections": [{"heading": "", "paragraphs": [
                {"text": "没有出处的段落", "cites": []},
            ]}],
        }
        report = compose.check_citations(article, blocks)
        assert report["grounded"] is False
        assert report["uncitedParagraphs"] == 1

    def test_invalid_cite_flagged(self) -> None:
        blocks = [{"ref": "A1", "file": "x.txt", "line": 1, "text": "", "kind": "archive"}]
        article = {
            "sections": [{"heading": "", "paragraphs": [
                {"text": "引用了不存在的编号", "cites": ["A99"]},
            ]}],
        }
        report = compose.check_citations(article, blocks)
        assert report["invalidCites"] == ["A99"]
        assert report["grounded"] is False

    def test_placeholder_paragraph_not_counted(self) -> None:
        article = {
            "sections": [{"heading": "", "paragraphs": [
                {"text": "（素材不足，待补充）", "cites": []},
            ]}],
        }
        report = compose.check_citations(article, [])
        assert report["paragraphCount"] == 0


class TestReviewArticle:
    def test_review_skips_submission_format_rules(self) -> None:
        """公众号文章不是投稿件：SUB-* 投稿格式规则不应出现在发前检查里。"""
        rules, _ = checker.load_rules()
        article = {
            "title": "一篇公众号文章",
            "lead": "导语",
            "sections": [{"heading": "正文", "paragraphs": [
                {"text": "Macau 与 Macao 的写法需要规范，括号用（全角）。", "cites": []},
            ]}],
        }
        report = compose.review_article(article, rules)
        assert all(not f["ruleId"].startswith("SUB") for f in report["findings"])


class TestMarkdown:
    def test_includes_title_sections_and_cites(self) -> None:
        article = compose.parse_article(json.dumps(_article_payload(), ensure_ascii=False))
        md = compose.article_to_markdown(article)
        assert "# 港城莞科研新进展" in md
        assert "## 科研" in md
        assert "[A1]" in md
        assert "配图建议" in md


class TestTitleHints:
    """职务对照表从 TITLE-001 规则生成，避免模型照抄素材里的泛称职务。"""

    def test_builds_mapping_from_rule(self) -> None:
        rules, _ = checker.load_rules()
        hint = compose._title_hints(rules)
        assert "李娟=副校长（学术）" in hint
        assert "不算编造" in hint

    def test_absent_rule_yields_empty(self) -> None:
        assert compose._title_hints([{"id": "ENG-001"}]) == ""
        assert compose._title_hints([]) == ""

    def test_rule_without_people_yields_empty(self) -> None:
        rules = [{"id": "TITLE-001", "params": {"people": []}}]
        assert compose._title_hints(rules) == ""

    def test_injected_into_system_prompt(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """成稿系统提示里必须带上职务口径，否则模型无从得知该补哪几个字。"""
        (tmp_path / "news_WX.txt").write_text("港城莞举行开学典礼\n", encoding="utf-8")
        monkeypatch.setenv("CAMPUS_CORPUS_DIR", str(tmp_path))
        settings = deepseek.Settings(deepseek_api_key="sk-test", deepseek_model="test-model")
        fake = _FakeAgentClient([
            {"choices": [{"message": {"role": "assistant", "content": json.dumps(_article_payload(), ensure_ascii=False)}}]}
        ])
        rules, _ = checker.load_rules()

        asyncio.run(compose.compose_article("写一篇开学典礼推文", rules, settings=settings, client=fake))

        system = fake.calls[0]["json"]["messages"][0]["content"]
        assert "【职务口径】" in system
        assert "李娟=副校长（学术）" in system


class TestComposeArticle:
    def test_without_key_returns_503(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            deepseek, "get_settings", lambda: deepseek.Settings(deepseek_api_key="")
        )
        r = client.post("/api/compose", json={"topic": "写一篇科研进展推文"})
        assert r.status_code == 503
        assert "DEEPSEEK_API_KEY" in r.json()["detail"]

    def test_short_topic_rejected(self, client: TestClient) -> None:
        assert client.post("/api/compose", json={"topic": "x"}).status_code == 422

    def test_full_pipeline_with_fake_client(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """端到端：检索真实语料 → 假模型返回文章 → 出处与规范校验。"""
        (tmp_path / "news_WX.txt").write_text("港城莞取得重大科研突破\n", encoding="utf-8")
        monkeypatch.setenv("CAMPUS_CORPUS_DIR", str(tmp_path))
        settings = deepseek.Settings(deepseek_api_key="sk-test", deepseek_model="test-model")
        payload = _article_payload()
        fake = _FakeAgentClient([
            {"choices": [{"message": {"role": "assistant", "content": json.dumps(payload, ensure_ascii=False)}}]}
        ])
        rules, _ = checker.load_rules()

        result = asyncio.run(compose.compose_article("写一篇科研突破推文", rules, settings=settings, client=fake))

        assert result["topic"] == "写一篇科研突破推文"
        assert result["article"]["title"] == payload["title"]
        assert result["citations"]["grounded"] is True
        assert result["sources"]
        assert "A1" in result["markdown"]
        assert result["review"]["counts"]["total"] >= 0
        assert result["model"] == "test-model"
        # 请求用了 JSON 模式，且上下文带编号素材
        sent = fake.calls[0]["json"]
        assert sent["response_format"] == {"type": "json_object"}
        assert "[A1]" in sent["messages"][1]["content"]

    def test_upstream_failure_maps_to_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import httpx

        settings = deepseek.Settings(deepseek_api_key="sk-test")
        rules, _ = checker.load_rules()

        class BrokenClient:
            async def __aenter__(self): return self
            async def __aexit__(self, *_a): return False
            async def aclose(self): return None
            async def post(self, *_a, **_k):
                raise httpx.ConnectError("boom")

        with pytest.raises(deepseek.DeepSeekUnavailable):
            asyncio.run(compose.compose_article("科研", rules, settings=settings, client=BrokenClient()))


BLOCKS = [{"ref": "A1", "kind": "wechat", "text": "学校取得科研突破", "file": "x_WX.txt", "line": 3}]


class TestReviseArticle:
    """改稿：沿用原素材编号，只按指令调整被点名的部分。"""

    def test_revise_reuses_material_refs(self) -> None:
        settings = deepseek.Settings(deepseek_api_key="sk-test", deepseek_model="test-model")
        revised_payload = _article_payload()
        revised_payload["title"] = "短标题"
        fake = _FakeAgentClient([
            {"choices": [{"message": {"role": "assistant", "content": json.dumps(revised_payload, ensure_ascii=False)}}]}
        ])
        rules, _ = checker.load_rules()
        article = compose.parse_article(json.dumps(_article_payload(), ensure_ascii=False))

        result = asyncio.run(
            compose.revise_article("科研进展", article, "标题再短一点", BLOCKS, [], rules, settings=settings, client=fake)
        )

        assert result["article"]["title"] == "短标题"
        assert result["instruction"] == "标题再短一点"
        assert result["citations"]["grounded"] is True
        assert result["meta"]["revised"] is True
        sent = fake.calls[0]["json"]["messages"]
        assert "标题再短一点" in sent[1]["content"]
        # 当前草稿与编号素材都要进上下文，否则模型改出来的引用会对不上
        assert "港城莞科研新进展" in sent[1]["content"]
        assert "[A1]" in sent[1]["content"]

    def test_empty_model_output_keeps_previous_draft(self) -> None:
        """模型返回不可解析内容时，保留原稿而不是覆盖成空白。"""
        settings = deepseek.Settings(deepseek_api_key="sk-test")
        fake = _FakeAgentClient([
            {"choices": [{"message": {"role": "assistant", "content": "抱歉，我无法完成"}}]}
        ])
        rules, _ = checker.load_rules()
        article = compose.parse_article(json.dumps(_article_payload(), ensure_ascii=False))

        result = asyncio.run(
            compose.revise_article("科研进展", article, "改标题", BLOCKS, [], rules, settings=settings, client=fake)
        )

        assert result["article"]["title"] == article["title"]
        assert result["article"]["sections"][0]["paragraphs"][0]["text"] == "据档案记载，学校取得进展。"

    def test_revise_endpoint_without_key_returns_503(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(deepseek, "get_settings", lambda: deepseek.Settings(deepseek_api_key=""))
        r = client.post(
            "/api/compose/revise",
            json={"topic": "科研", "instruction": "标题短一点", "article": _article_payload(), "sources": BLOCKS},
        )
        assert r.status_code == 503

    def test_blank_instruction_rejected(self, client: TestClient) -> None:
        r = client.post(
            "/api/compose/revise",
            json={"instruction": "", "article": _article_payload(), "sources": BLOCKS},
        )
        assert r.status_code == 422
