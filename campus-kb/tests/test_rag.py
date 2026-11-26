"""RAG 语义检索测试。

原则：单测不依赖真实 embedding 模型（95MB，不能要求测试环境下载）。
  - 默认 CAMPUS_EMBEDDING=off，锁住纯 BM25 降级路径；
  - 稠密路用 _FakeModel 注入假向量，验证混合召回 / 索引落盘 / 失效重建的逻辑；
  - 真实语义召回效果另用真实模型端到端验证（见 README 开发日志）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import rag, search
from api.main import app
from api.search import Doc


@pytest.fixture(autouse=True)
def clean_rag(monkeypatch, tmp_path):
    monkeypatch.setenv("CAMPUS_INDEX_DIR", str(tmp_path / "idx"))
    monkeypatch.setenv("CAMPUS_EMBEDDING", "off")
    rag.clear_caches()
    yield
    rag.clear_caches()


class _FakeModel:
    """固定维度假向量：按文本长度与「心理」词频产生可区分的相似度。"""

    def __init__(self) -> None:
        self.embed_calls = 0

    def embed(self, texts):
        for t in texts:
            self.embed_calls += 1
            yield [float(len(t) % 11 + 1), float(t.count("心理") + 1), 1.0]

    def query_embed(self, texts):
        return self.embed(texts)


@pytest.fixture
def fake_model(monkeypatch, tmp_path):
    monkeypatch.setenv("CAMPUS_EMBEDDING", "auto")
    rag.clear_caches()
    model = _FakeModel()
    rag._model = model
    rag._model_failed = False
    yield model
    rag.clear_caches()


def _corpus(tmp_path: Path, files: dict[str, str]) -> str:
    root = tmp_path / "text"
    root.mkdir()
    for name, text in files.items():
        (root / f"{name}.txt").write_text(text, encoding="utf-8")
    return str(root)


# ---------- 分块与出处 ----------

def test_chunks_keep_real_line_numbers():
    docs = (Doc("a", "标题\n\n" + "第一段" * 100 + "\n" + "第二段" * 100),)
    chunks = rag.build_chunks(docs)
    assert chunks
    lines = docs[0].text.split("\n")
    for c in chunks:
        assert c.file == "a"
        assert 1 <= c.start_line <= c.end_line <= len(lines)
        assert c.text.strip()
        # start_line 指向的原文必须真的出现在这个块里
        assert lines[c.start_line - 1].strip()[:6] in c.text


def test_long_single_line_is_split_with_same_line_number():
    chunks = rag.build_chunks((Doc("a", "研" * 1000),))
    assert len(chunks) >= 3
    assert all(c.start_line == c.end_line == 1 for c in chunks)


def test_chunks_have_overlap_on_boundary():
    # 相邻块共享边界行，避免一句话被切断后两半都检索不到
    docs = (Doc("a", "\n".join(f"第{i}行内容" * 40 for i in range(1, 12))),)
    chunks = rag.build_chunks(docs)
    assert len(chunks) >= 2
    assert any(a.end_line == b.start_line for a, b in zip(chunks, chunks[1:]))


# ---------- BM25 / RRF ----------

def test_bm25_ranks_relevant_chunk_first():
    chunks = rag.build_chunks(
        (Doc("psy", "心理咨询预约地点在学生公寓四栋 " * 12), Doc("robot", "巡检机器人与机械臂传感 " * 12))
    )
    ranked = rag.BM25Index(chunks).rank("心理咨询")
    assert ranked
    assert chunks[ranked[0][0]].file == "psy"


def test_rrf_favours_item_present_in_both_rankings():
    fused = rag._rrf([[(1, 3.0), (2, 2.0)], [(2, 0.9), (3, 0.8)]])
    assert fused[0][0] == 2          # 两路都命中
    assert fused[0][2] == 0b11


# ---------- 降级与模式 ----------

def test_hybrid_degrades_to_keyword_without_model(tmp_path):
    root = _corpus(
        tmp_path,
        {"psy": "心理咨询预约地点在学生公寓四栋\n" + "心理成长中心开放时间\n" * 3,
         "sci": "科研进展与产学研融合\n" * 5},
    )
    r = search.search("心理咨询", root=root, mode="hybrid")
    assert r["retrieval"]["degraded"] is True
    assert r["retrieval"]["dense"] is False
    assert r["results"]
    assert all(x["matchedBy"] == "keyword" for x in r["results"])
    assert r["results"][0]["file"] == "psy"
    assert r["results"][0]["endLine"] >= r["results"][0]["line"]


def test_semantic_mode_falls_back_instead_of_returning_nothing(tmp_path):
    root = _corpus(tmp_path, {"psy": "心理咨询预约方式 " * 20})
    r = search.search("心理", root=root, mode="semantic")
    assert r["results"]  # 不能因为模型缺失就交白卷
    assert all(x["matchedBy"] == "keyword" for x in r["results"])


def test_strict_mode_keeps_old_and_behaviour(tmp_path):
    root = _corpus(
        tmp_path,
        {"a": "心理热线 400-098-2525\n只有心理两字没有别的\n"},
    )
    both = search.search("心理 热线", root=root, mode="strict")
    assert len(both["results"]) == 1
    assert "热线" in both["results"][0]["excerpt"]
    assert both["results"][0]["matchedBy"] == "strict"


def test_result_exposes_full_chunk_text(tmp_path):
    """列表摘要可以短，但成稿链路拿到的必须是完整块。"""
    root = _corpus(
        tmp_path,
        {"a": "学校概况与办学理念 " * 8 + "2027年QS世界大学排名位列第52位\n"},
    )
    r = search.search("学校QS排名", root=root)
    assert r["results"]
    assert "第52位" in r["results"][0]["text"]
    assert len(r["results"][0]["text"]) > len(r["results"][0]["excerpt"])


def test_unknown_mode_is_treated_as_hybrid(tmp_path):
    root = _corpus(tmp_path, {"a": "产学研融合 " * 20})
    r = search.search("融合", root=root, mode="whatever")
    assert r["results"]
    assert r["mode"] == "whatever"  # 记录原值，但内部按 hybrid 处理


def test_empty_query_returns_nothing(tmp_path):
    root = _corpus(tmp_path, {"a": "产学研融合 " * 20})
    assert search.search("   ", root=root)["results"] == []


# ---------- 稠密路 / 索引缓存 ----------

def test_hybrid_uses_dense_path_and_writes_index(tmp_path, fake_model):
    root = _corpus(
        tmp_path,
        {"psy": "心理咨询预约地点在学生公寓四栋\n" + "心理成长中心 " * 30,
         "sci": "科研进展与产学研融合 " * 30},
    )
    r = search.search("心理", root=root, mode="hybrid")
    assert r["retrieval"]["dense"] is True
    assert r["retrieval"]["chunks"] > 0
    assert fake_model.embed_calls > 0
    assert any(x["matchedBy"] in {"hybrid", "semantic"} for x in r["results"])
    index_files = list((tmp_path / "idx").glob("vectors-*.json"))
    assert len(index_files) == 1
    data = json.loads(index_files[0].read_text(encoding="utf-8"))
    assert data["model"] == rag.MODEL_NAME
    assert len(data["vectors"]) == data["chunks"]


def test_index_build_batches_embed_to_cap_memory(monkeypatch, tmp_path, fake_model):
    """全量重建时分批编码，避免一次性把数千 chunks 塞进 ONNX 撑爆内存。"""
    batches: list[int] = []
    real_embed = fake_model.embed

    def tracked_embed(texts):
        batches.append(len(texts))
        yield from real_embed(texts)

    monkeypatch.setattr(fake_model, "embed", tracked_embed)
    # 造出远超单批上限的块数
    root = _corpus(tmp_path, {"big": "\n".join(f"第{i}行科研内容 " * 12 for i in range(1, 25))})
    search.search("科研", root=root)
    assert batches
    assert max(batches) <= rag._EMBED_BATCH
    assert len(batches) >= 2


def test_index_is_reused_not_recomputed(tmp_path, fake_model):
    root = _corpus(tmp_path, {"a": "产学研融合与科研成果 " * 40})
    search.search("科研", root=root)
    first = fake_model.embed_calls
    search.search("成果", root=root)
    # 第二次只编码 query，不再重算全部 chunk
    assert fake_model.embed_calls == first + 1


def test_index_rebuilds_when_corpus_changes(tmp_path, fake_model):
    root = _corpus(tmp_path, {"a": "产学研融合 " * 30})
    search.search("融合", root=root)
    (Path(root) / "b.txt").write_text("新增的心理咨询档案 " * 30, encoding="utf-8")
    r = search.search("融合", root=root)
    assert r["scanned"] == 2          # 版本戳变化后新语料立刻可见
    assert len(list((tmp_path / "idx").glob("vectors-*.json"))) == 2


# ---------- HTTP 接口 ----------

def test_api_search_exposes_mode_and_retrieval():
    client = TestClient(app)
    resp = client.get("/api/search", params={"q": "心理", "mode": "keyword", "limit": 3})
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "keyword"
    assert "retrieval" in body
    assert body["retrieval"]["dense"] is False
    assert len(body["results"]) <= 3


def test_api_search_semantic_mode_degrades_cleanly():
    client = TestClient(app)
    resp = client.get("/api/search", params={"q": "产学研", "mode": "semantic", "limit": 3})
    assert resp.status_code == 200
    assert isinstance(resp.json()["results"], list)
