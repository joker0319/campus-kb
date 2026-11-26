"""往期公众号档案：元数据读取、时间倒序、筛选与安全边界。"""

import json

import pytest
from fastapi.testclient import TestClient

from api import archive
from api.main import app


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    """临时语料目录 + 上一级 sources 文件，与 Docker 挂载布局一致。"""
    text = tmp_path / "corpus" / "text"
    text.mkdir(parents=True)
    articles = [
        {
            "url": "https://mp.weixin.qq.com/s/aaa",
            "title": "九月活动回顾",
            "published": "2026-09-02",
            "file": "九月活动_20260902_WX.txt",
            "chars": 120,
            "images": 3,
        },
        {
            "url": "https://mp.weixin.qq.com/s/bbb",
            "title": "十一月科研进展",
            "published": "2026-11-19",
            "file": "十一月科研_20261119_WX.txt",
            "chars": 200,
            "images": 5,
        },
        {
            "url": "",
            "title": "无原文链接的草稿",
            "published": "2026-10-01",
            "file": "草稿_20261001_WX.txt",
            "chars": 50,
            "images": 0,
        },
    ]
    (text.parent / "wechat-sources.json").write_text(
        json.dumps({"articles": articles}, ensure_ascii=False), encoding="utf-8"
    )
    (text / "九月活动_20260902_WX.txt").write_text(
        "九月活动回顾\n[图1]\n这是一段关于校园开放日的记录。\n", encoding="utf-8"
    )
    (text / "十一月科研_20261119_WX.txt").write_text(
        "十一月科研进展\n团队在新材料方向取得突破。\n", encoding="utf-8"
    )
    monkeypatch.setenv("CAMPUS_CORPUS_DIR", str(text))
    return text


class TestArchiveList:
    def test_sorted_desc_and_months(self, corpus) -> None:
        result = archive.list_articles()
        assert result["total"] == 2  # 无链接的草稿被排除
        assert [a["published"] for a in result["articles"]] == ["2026-11-19", "2026-09-02"]
        assert result["months"] == [
            {"month": "2026-11", "count": 1},
            {"month": "2026-09", "count": 1},
        ]

    def test_excerpt_skips_title_and_image_placeholders(self, corpus) -> None:
        article = next(a for a in archive.list_articles()["articles"] if a["month"] == "2026-09")
        assert article["excerpt"] == "这是一段关于校园开放日的记录。"
        assert "[图1]" not in article["excerpt"]
        assert article["url"].startswith("https://mp.weixin.qq.com/")

    def test_search_matches_title_and_body(self, corpus) -> None:
        assert archive.list_articles("科研")["total"] == 1
        assert archive.list_articles("校园开放日")["total"] == 1  # 命中正文摘要
        assert archive.list_articles("不存在的词")["total"] == 0

    def test_month_filter(self, corpus) -> None:
        result = archive.list_articles(month="2026-11")
        assert result["total"] == 1
        assert result["articles"][0]["title"] == "十一月科研进展"

    def test_month_options_stay_full_when_filtered(self, corpus) -> None:
        """筛选后月份选项仍基于全量，下拉框不会丢掉其它月份。"""
        result = archive.list_articles(month="2026-11")
        assert result["months"] == [
            {"month": "2026-11", "count": 1},
            {"month": "2026-09", "count": 1},
        ]
        searched = archive.list_articles("科研")
        assert searched["total"] == 1
        assert len(searched["months"]) == 2

    def test_missing_sources_degrades(self, corpus, monkeypatch) -> None:
        monkeypatch.setenv("CAMPUS_CORPUS_DIR", str(corpus / "missing"))
        result = archive.list_articles()
        assert result["total"] == 0
        assert result["articles"] == []


class TestArchiveArticle:
    def test_returns_local_text(self, corpus) -> None:
        detail = archive.article_detail("十一月科研_20261119_WX.txt")
        assert detail["title"] == "十一月科研进展"
        assert "新材料方向取得突破" in detail["text"]
        assert detail["url"].startswith("https://mp.weixin.qq.com/")

    @pytest.mark.parametrize("bad", ["../secret.txt", "/etc/passwd", "a/b_WX.txt", "notes.txt"])
    def test_rejects_unsafe_file_names(self, corpus, bad: str) -> None:
        with pytest.raises(ValueError):
            archive.article_detail(bad)

    def test_missing_file_raises_lookup(self, corpus) -> None:
        with pytest.raises(LookupError):
            archive.article_detail("不存在_20260101_WX.txt")


class TestArchiveEndpoints:
    @pytest.fixture
    def client(self) -> TestClient:
        return TestClient(app)

    def test_list_endpoint(self, client: TestClient) -> None:
        response = client.get("/api/archive")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 0
        assert "months" in data and "articles" in data

    def test_article_endpoint_rejects_path_traversal(self, client: TestClient) -> None:
        response = client.get("/api/archive/article", params={"file": "../secret.txt"})
        assert response.status_code == 400

    def test_article_endpoint_404(self, client: TestClient) -> None:
        response = client.get("/api/archive/article", params={"file": "不存在_20260101_WX.txt"})
        assert response.status_code == 404
