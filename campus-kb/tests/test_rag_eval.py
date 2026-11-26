"""RAG 评测基线回归：防止改分块 / 改语料后召回悄悄退化。

测试不加载真实 embedding（95MB），只锁纯 BM25 的确定性基线；
混合检索基线由 `python -m evals.rag_eval --mode hybrid` 手工跑并记录在 README。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from api import rag
from evals.rag_eval import evaluate, load_cases, validate_cases


@pytest.fixture(autouse=True)
def offline_rag(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("CAMPUS_EMBEDDING", "off")
    monkeypatch.setenv("CAMPUS_INDEX_DIR", str(tmp_path / "idx"))
    rag.clear_caches()
    yield
    rag.clear_caches()


def test_cases_are_valid() -> None:
    """公开档每条期望都必须真的在语料中，否则基线没有意义。"""
    cases = load_cases()
    assert len(cases) >= 20
    assert all(c.get("scope", "public") == "public" for c in cases)
    validate_cases(cases)


def test_internal_cases_are_only_loaded_explicitly() -> None:
    """内部档案用例默认不参与公开档基线。"""
    assert len(load_cases()) < len(load_cases(scope="all"))


def test_keyword_baseline_does_not_regress() -> None:
    cases = load_cases()
    report = evaluate(cases, mode="keyword", k=5)
    summary = report["summary"]

    assert summary["scope"] == "public"
    assert summary["cases"] == len(cases)
    assert summary["degraded"] is True
    assert summary["hit_at_k"] >= 0.85
    assert summary["mrr"] >= 0.75


def test_internal_keyword_baseline_does_not_regress() -> None:
    """显式 all 档仍能评测内部档案用例，检索时不退化。"""
    from api.search import SCOPE_ALL

    cases = load_cases(scope=SCOPE_ALL)
    report = evaluate(cases, mode="keyword", k=5, scope=SCOPE_ALL)
    summary = report["summary"]

    assert summary["cases"] == len(cases)
    assert summary["hit_at_k"] >= 0.85
    assert summary["mrr"] >= 0.75
