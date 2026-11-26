"""Agent 只读扩展工具：规范版本对比、跨档案时间线。

用临时语料验证时间线的日期解析与排序；版本对比读仓库权威口径文件。
"""

import pytest

import checker
from api import agent


@pytest.fixture
def executor():
    rules, _ = checker.load_rules()
    return agent.make_executor(rules)


class TestCompareRuleVersions:
    def test_reports_canonical_version_and_superseded_value(self, executor) -> None:
        result = executor("compare_rule_versions", {"topic": "排名"})
        data = result["structured"]

        assert data["kind"] == "versionDiff"
        assert data["canonical"] == "20260618"
        assert "2026.05" in data["superseded"]
        assert data["changes"]
        assert data["changes"][0]["current"] == "第52位"
        assert 63 in data["changes"][0]["old"]
        assert "第52位" in result["text"] and "63" in result["text"]

    def test_topic_filters_unrelated_facts(self, executor) -> None:
        result = executor("compare_rule_versions", {"topic": "标点"})
        assert result["structured"]["changes"] == []
        assert "未记录" in result["text"]

    def test_empty_topic_returns_all_with_rule_sources(self, executor) -> None:
        result = executor("compare_rule_versions", {})
        assert result["structured"]["changes"]
        assert result["structured"]["ruleVersions"].get("20260618")

    def test_missing_authority_degrades_without_crash(self, executor, monkeypatch) -> None:
        monkeypatch.setattr(checker, "load_authority", lambda: {})
        result = executor("compare_rule_versions", {"topic": "排名"})
        assert result["structured"]["canonical"] == ""
        assert result["structured"]["changes"] == []


class TestArchiveTimeline:
    def test_dates_sorted_and_one_entry_per_archive(
        self, executor, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setenv("CAMPUS_CORPUS_DIR", str(tmp_path))
        (tmp_path / "活动A_20260101_WX.txt").write_text(
            "开学典礼致辞\n第二行也提开学典礼\n", encoding="utf-8"
        )
        # 用 _WX 后缀：内部档案默认不进检索池，日期解析仍按 DDMMYY 验证
        (tmp_path / "活动B_130421_WX.txt").write_text(
            "开学典礼与奠基\n", encoding="utf-8"
        )
        (tmp_path / "无日期档案.txt").write_text("开学典礼记录\n", encoding="utf-8")

        result = executor("archive_timeline", {"topic": "开学典礼"})
        data = result["structured"]

        assert data["kind"] == "timeline"
        # DDMMYY 需按 20 世纪后推，且与 YYYYMMDD 混排后升序
        assert [item["date"] for item in data["items"]] == ["2021-04-13", "2026-01-01"]
        assert len(data["undated"]) == 1
        assert sum("活动A" in item["file"] for item in data["items"]) == 1
        assert "无日期" in result["text"]

    def test_empty_topic_returns_prompt(self, executor) -> None:
        result = executor("archive_timeline", {})
        assert result["structured"]["items"] == []
        assert "主题为空" in result["text"]

    def test_no_hits_states_missing(self, executor, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("CAMPUS_CORPUS_DIR", str(tmp_path))
        (tmp_path / "无关_WX.txt").write_text("与主题无关的内容\n", encoding="utf-8")
        result = executor("archive_timeline", {"topic": "完全不存在的话题"})
        assert result["structured"]["items"] == []
        assert "未检索到" in result["text"]


def test_readonly_tools_are_declared_alongside_review_gate() -> None:
    names = [tool["function"]["name"] for tool in agent.TOOLS]
    assert "compare_rule_versions" in names
    assert "archive_timeline" in names
    # 稿件规范校验仍作为生成后的质量关卡留在工具集里
    assert "review_draft" in names
