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
    """评测集里的每条期望都必须真的在语料中，否则基线没有意义。"""
    cases = load_cases()
    assert len(cases) >= 20
    validate_cases(cases)


def test_keyword_baseline_does_not_regress() -> None:
    cases = load_cases()
    report = evaluate(cases, mode="keyword", k=5)
    summary = report["summary"]

    assert summary["cases"] == len(cases)
    assert summary["degraded"] is True
    assert summary["hit_at_k"] >= 0.85
    assert summary["mrr"] >= 0.75
