"""权威口径（authority.json）回归测试。

用户 2026-11-24 裁决：QS 2027 = 52、规范版本 20260618 为准、2026.05 与
带 (2) 的副本忽略。这里锁死单一事实源、规则判错行为、基线数量，
以及口径是否真的注入到 Agent 与文章生成的提示里。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import checker
from api import agent, compose

KB_ROOT = Path(checker.ROOT)
RULES_DIR = KB_ROOT / "rules"


@pytest.fixture(scope="module")
def authority():
    return json.loads((KB_ROOT / "authority.json").read_text(encoding="utf-8"))


class TestAuthorityFile:
    def test_version_and_superseded(self, authority):
        manual = authority["manual"]
        assert manual["canonical_version"] == "20260618"
        assert "2026.05" in manual["superseded"]
        assert manual["ignored_copies"], "必须显式声明被忽略的副本"

    def test_qs_2027_value(self, authority):
        fact = authority["facts"]["QS_2027"]
        assert fact["value"] == 52
        assert fact["canonical_text"] == "第52位"
        assert 63 in fact["rejected_values"]
        assert "52nd" in fact["note"]

    def test_evidence_files_exist(self, authority):
        """裁决不是凭空拍板：引用的两篇官方推文必须真实在语料里。"""
        paths = authority["facts"]["QS_2027"]["evidence"]
        assert paths
        for rel in paths:
            assert (KB_ROOT / rel).is_file(), rel

    def test_rank_rule_matches_single_source(self, authority):
        """rank.json 的兜底值必须与单一事实源一致，防止两处硬编码漂移。"""
        rank = json.loads((RULES_DIR / "rank.json").read_text(encoding="utf-8"))
        rule = rank["rules"][0]
        assert rule["params"]["authority_key"] == "QS_2027"
        assert rule["params"]["authoritative"] == authority["facts"]["QS_2027"]["value"]

    def test_no_stale_version_in_rule_sources(self):
        """所有手册类规则出处统一 20260618，旧版 2026.05 不得回潮。"""
        seen = 0
        for p in RULES_DIR.glob("*.json"):
            src = json.loads(p.read_text(encoding="utf-8")).get("source", "")
            if "常用表述规范手册" in src:
                seen += 1
                assert "20260618" in src, p.name
                assert "2026.05" not in src, p.name
        assert seen >= 5


@pytest.fixture(scope="module")
def rules():
    loaded, skipped = checker.load_rules()
    assert not skipped
    assert len(loaded) == 19
    return loaded


class TestCheckerAuthority:
    def test_load_and_brief(self, authority):
        assert checker.load_authority()["manual"]["canonical_version"] == "20260618"
        brief = checker.authority_brief()
        assert "20260618" in brief
        assert "第52位" in brief
        assert "忽略" in brief

    def test_canonical_value_passes(self, rules):
        findings = checker.run("香港城市大学在2027年QS世界大学排名位列第52位。", rules, mode="archive")
        assert not [f for f in findings if f["rule_id"] == "RANK-001"]

    def test_rejected_value_is_flagged(self, rules):
        """只写一个错误数值也要判错——这是本次升级新增的能力。"""
        findings = checker.run("香港城市大学在2027年QS世界大学排名位列第63位。", rules, mode="archive")
        rank = [f for f in findings if f["rule_id"] == "RANK-001"]
        assert len(rank) == 1
        assert "权威口径第 52 位" in rank[0]["message"]
        assert "20260618" in rank[0]["suggestion"]
        assert "副本一律忽略" in rank[0]["suggestion"]

    def test_conflict_is_still_one_finding(self, rules):
        """冲突与偏离合并为一条命中，坏样例基线数量不变。"""
        findings = checker.run(
            "在2027年QS排名位列第63位，在QS 2027排名中位列52nd。", rules, mode="archive"
        )
        rank = [f for f in findings if f["rule_id"] == "RANK-001"]
        assert len(rank) == 1
        assert "[52, 63]" in rank[0]["message"]
        assert "权威口径" in rank[0]["message"]

    def test_sample_baselines_unchanged(self, rules):
        good = (KB_ROOT / "samples/good-draft.md").read_text(encoding="utf-8")
        bad = (KB_ROOT / "samples/bad-draft.md").read_text(encoding="utf-8")
        assert checker.run(good, rules) == [], "合规样例须 0 命中"
        assert len(checker.run(bad, rules)) == 17, "坏样例基线须保持 17 项"


class TestPromptInjection:
    def test_agent_system_prompt_has_authority(self):
        assert "【权威口径】" in agent.SYSTEM_PROMPT
        assert "20260618" in agent.SYSTEM_PROMPT
        assert "第52位" in agent.SYSTEM_PROMPT

    def test_compose_context_has_constraint(self):
        ctx = compose.build_context([], [])
        assert "【口径约束】" in ctx
        assert "20260618" in ctx
        assert "第52位" in ctx
        assert "不可作为 [A#] 引用" in ctx
        assert "【素材库】" in ctx
