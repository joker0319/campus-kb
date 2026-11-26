"""语料可见范围隔离：内部档案默认不进成稿 / Agent / 公开检索。

P0 发布底线：`*_DOCUMENT.txt`（行程、采购论证、手机号等内部档案）
不能因为混在同一个检索池里被模型引用进公众号文章。
显式 `scope="all"` 只给人工核查用，且向量索引按 scope 隔离，两档不互相覆盖。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import checker
from api import agent, compose
from api.main import app
from api.search import SCOPE_ALL, SCOPE_PUBLIC, _corpus_stamp, load_corpus, search


@pytest.fixture()
def mixed_root(tmp_path: Path) -> Path:
    """一份公开推文 + 一份内部档案，含同一个主题词，确保两档都会被命中。"""
    (tmp_path / "公开_WX.txt").write_text(
        "学校取得重要科研进展，公开可发。\n" * 4, encoding="utf-8"
    )
    (tmp_path / "内部行程_DOCUMENT.txt").write_text(
        "内部科研进展行程安排，联系人 13600000000。\n" * 4, encoding="utf-8"
    )
    return tmp_path


class TestLoadScope:
    def test_default_public_excludes_internal(self, mixed_root: Path) -> None:
        docs = load_corpus(str(mixed_root))
        assert [d.name for d in docs] == ["公开_WX"]
        assert search("科研进展", root=str(mixed_root))["scanned"] == 1

    def test_explicit_all_includes_internal(self, mixed_root: Path) -> None:
        docs = load_corpus(str(mixed_root), scope=SCOPE_ALL)
        assert sorted(d.name for d in docs) == ["公开_WX", "内部行程_DOCUMENT"]
        assert search("科研进展", root=str(mixed_root), scope=SCOPE_ALL)["scanned"] == 2

    def test_unknown_scope_is_rejected(self, mixed_root: Path) -> None:
        with pytest.raises(ValueError, match="未知检索范围"):
            load_corpus(str(mixed_root), scope="secret")

    def test_index_stamps_do_not_collide(self, mixed_root: Path) -> None:
        """public 恒偶数、all 恒奇数：向量索引文件名不会互相覆盖。"""
        pub = _corpus_stamp(mixed_root, SCOPE_PUBLIC)
        all_ = _corpus_stamp(mixed_root, SCOPE_ALL)
        assert pub % 2 == 0 and all_ % 2 == 1 and pub != all_

    def test_internal_file_change_does_not_bump_public_stamp(
        self, mixed_root: Path
    ) -> None:
        import time

        before = _corpus_stamp(mixed_root, SCOPE_PUBLIC)
        time.sleep(0.01)
        (mixed_root / "内部行程_DOCUMENT.txt").write_text("新的内部行程 13600000000\n", encoding="utf-8")
        assert _corpus_stamp(mixed_root, SCOPE_PUBLIC) == before
        assert _corpus_stamp(mixed_root, SCOPE_ALL) != before


class TestSearchScope:
    def test_public_results_never_carry_internal_file(self, mixed_root: Path) -> None:
        result = search("科研进展", root=str(mixed_root))
        assert result["scope"] == SCOPE_PUBLIC
        assert result["results"]
        assert all(not r["file"].endswith("_DOCUMENT") for r in result["results"])

    def test_all_results_can_carry_internal_file(self, mixed_root: Path) -> None:
        result = search("科研进展", root=str(mixed_root), scope=SCOPE_ALL)
        assert result["scope"] == SCOPE_ALL
        assert any(r["file"].endswith("_DOCUMENT") for r in result["results"])


class TestComposeScope:
    def test_gather_material_ignores_internal_archive(
        self, monkeypatch: pytest.MonkeyPatch, mixed_root: Path
    ) -> None:
        monkeypatch.setenv("CAMPUS_CORPUS_DIR", str(mixed_root))
        rules, _ = checker.load_rules()
        blocks, _, meta = compose.gather_material("科研进展", rules)
        assert blocks
        assert all(not b["file"].endswith("_DOCUMENT.txt") for b in blocks)
        assert meta["scanned"] == 1


class TestAgentScope:
    def test_search_archive_ignores_internal_archive(
        self, monkeypatch: pytest.MonkeyPatch, mixed_root: Path
    ) -> None:
        monkeypatch.setenv("CAMPUS_CORPUS_DIR", str(mixed_root))
        rules, _ = checker.load_rules()
        result = agent.make_executor(rules)("search_archive", {"query": "科研进展"})
        items = result["structured"]["items"]
        assert items
        assert all(not item["file"].endswith("_DOCUMENT") for item in items)

    def test_timeline_ignores_internal_archive(
        self, monkeypatch: pytest.MonkeyPatch, mixed_root: Path
    ) -> None:
        monkeypatch.setenv("CAMPUS_CORPUS_DIR", str(mixed_root))
        rules, _ = checker.load_rules()
        result = agent.make_executor(rules)("archive_timeline", {"topic": "科研进展"})
        data = result["structured"]
        assert all(not item["file"].endswith("_DOCUMENT") for item in data["items"])
        assert all(not item["file"].endswith("_DOCUMENT") for item in data["undated"])


class TestHttpScope:
    @pytest.fixture()
    def client(self) -> TestClient:
        return TestClient(app)

    def test_endpoint_default_hides_internal(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, mixed_root: Path
    ) -> None:
        import api.main as m

        original = m.corpus_search.corpus_dir
        monkeypatch.setattr(m.corpus_search, "corpus_dir", lambda: mixed_root)
        try:
            resp = client.get("/api/search", params={"q": "科研进展"})
            assert resp.status_code == 200
            body = resp.json()
            assert body["scope"] == SCOPE_PUBLIC
            assert body["scanned"] == 1
            assert all(not r["file"].endswith("_DOCUMENT") for r in body["results"])
        finally:
            monkeypatch.setattr(m.corpus_search, "corpus_dir", original)

    def test_endpoint_all_is_explicit(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch, mixed_root: Path
    ) -> None:
        import api.main as m

        original = m.corpus_search.corpus_dir
        monkeypatch.setattr(m.corpus_search, "corpus_dir", lambda: mixed_root)
        try:
            resp = client.get("/api/search", params={"q": "科研进展", "scope": SCOPE_ALL})
            assert resp.status_code == 200
            body = resp.json()
            assert body["scanned"] == 2
            assert any(r["file"].endswith("_DOCUMENT") for r in body["results"])
        finally:
            monkeypatch.setattr(m.corpus_search, "corpus_dir", original)

    def test_endpoint_rejects_unknown_scope(
        self, client: TestClient, mixed_root: Path
    ) -> None:
        resp = client.get("/api/search", params={"q": "科研进展", "scope": "secret"})
        assert resp.status_code == 400
