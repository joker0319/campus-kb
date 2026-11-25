"""港澳台表述规则（rules/sovereignty.json）回归测试。

规则依据：《香港城市大学（东莞）常用表述规范手册 20260618》三、常用信息：
港澳台与领土主权。用户 2026-11-25 裁决：SOEV-003 保持 error，不降级，
只补专有名词豁免（「港澳台侨联招」这类全称改了就错）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import checker

RULES = json.loads(
    (Path(checker.ROOT) / "rules" / "sovereignty.json").read_text(encoding="utf-8")
)["rules"]
BY_ID = {r["id"]: r for r in RULES}


def hits(rule_id: str, text: str) -> list[dict]:
    return checker.HANDLERS[BY_ID[rule_id]["type"]](BY_ID[rule_id], text)


class TestRequireContext:
    """SOEV-003：集体表述港澳台须带「地区/同胞/暨」。"""

    @pytest.mark.parametrize(
        "text",
        [
            "港澳台及国际生同期入学",
            "港澳台学生28人、国际新生6人",
            "港澳台和国际媒体均有报道",
            "面向港澳台招生",
        ],
    )
    def test_bare_mention_flagged(self, text):
        assert len(hits("SOEV-003", text)) == 1, text

    @pytest.mark.parametrize(
        "text",
        [
            "港澳台地区学生28人",
            "港澳台同胞共叙情谊",
            "海峡两岸暨港澳台青年论坛",
        ],
    )
    def test_qualified_mention_passes(self, text):
        assert hits("SOEV-003", text) == [], text

    @pytest.mark.parametrize(
        "text",
        [
            "港澳台侨联招、台湾学测、香港中学文凭考试均可报考",
            "校港澳台办负责对接",
            "港澳台事务办公室设在国际交流处",
        ],
    )
    def test_proper_noun_exempt(self, text):
        """专有名词豁免：改了反而错，不应报错。"""
        assert hits("SOEV-003", text) == [], text

    def test_exempt_does_not_leak_to_neighbors(self):
        """豁免只覆盖命中区间，同句其他裸写仍要报。"""
        text = "港澳台侨联招录取6人，港澳台学生28人"
        found = hits("SOEV-003", text)
        assert len(found) == 1
        assert found[0]["hit"] == "港澳台"

    def test_exclude_configured(self):
        term = BY_ID["SOEV-003"]["params"]["terms"][0]
        assert term["exclude"], "专有名词豁免必须显式声明，禁止散落在代码里"
        assert "港澳台侨" in term["exclude"]


class TestOtherSovereigntyRules:
    def test_macau_flagged_but_university_exempt(self):
        assert hits("SOEV-001", "赴澳门（Macau）交流") != []
        assert hits("SOEV-001", "澳门大学（University of Macau）") == []

    def test_parallel_wording_forbidden(self):
        assert hits("SOEV-002", "中、港、台三地学者参会") != []
        assert hits("SOEV-002", "两岸四地高校论坛") != []
        assert hits("SOEV-002", "海峡两岸暨香港高校论坛") == []

    def test_formal_document_needs_sovereignty(self):
        assert hits("SOEV-004", "香港、澳门、台湾地区学生") != []
        assert hits("SOEV-004", "中国香港、中国澳门和中国台湾地区学生") == []
