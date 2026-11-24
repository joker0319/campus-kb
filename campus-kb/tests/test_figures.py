"""配图推荐：筛选、排序、去重、弱命中标注，以及下发接口。

索引文件在 corpus/images（含真实师生影像，不入库），所以测试自己造一份
临时索引，指到 figures.INDEX 上，避免依赖本机语料状态。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import figures
from api.main import app


@pytest.fixture()
def fake_index(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """造一个 6 张图的小图库，覆盖实景/合影/图表/海报/肖像/二维码。"""
    root = tmp_path / "images"
    (root / "某篇推文").mkdir(parents=True)
    items = [
        ("f0001", "水下机器人正在水池中测试", "scene"),
        ("f0002", "机器人队合影", "crowd"),
        ("f0003", "榜单数据截图", "chart"),
        ("f0004", "招生长图海报", "poster"),
        ("f0005", "学生单人肖像", "portrait"),
        ("f0006", "二维码", "qr"),
    ]
    payload = []
    for fid, caption, kind in items:
        name = f"{fid}.png"
        (root / "某篇推文" / name).write_bytes(b"\x89PNG\r\n\x1a\n" + fid.encode())
        payload.append(
            {
                "id": fid,
                "article": "某篇推文",
                "title": "水下机器人国赛夺魁",
                "published": "2026-10-29",
                "file": name,
                "w": 1080,
                "h": 720,
                "kb": 300,
                "caption": caption,
                "kind": kind,
            }
        )
    index = root / "INDEX.json"
    index.write_text(json.dumps({"version": 1, "images": payload}, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(figures, "IMAGES", root)
    monkeypatch.setattr(figures, "INDEX", index)
    figures._cached.cache_clear()
    figures._terms.cache_clear()
    figures._paths.cache_clear()
    yield index
    figures._cached.cache_clear()
    figures._terms.cache_clear()
    figures._paths.cache_clear()


def _section(heading: str, text: str) -> dict:
    return {"heading": heading, "paragraphs": [{"text": text}]}


class TestFiltering:
    def test_portrait_and_qr_never_recommended(self, fake_index: Path) -> None:
        rows = figures.recommend([_section("机器人队合影与水下机器人", "水下机器人正在水池中测试")])
        kinds = {row["kind"] for row in rows}
        assert "portrait" not in kinds
        assert "qr" not in kinds

    def test_available_counts_only_usable(self, fake_index: Path) -> None:
        # 6 张里肖像与二维码被排除
        assert figures.available() == 4

    def test_missing_index_is_explicit(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(figures, "INDEX", tmp_path / "nope.json")
        figures._cached.cache_clear()
        assert figures.available() == 0
        with pytest.raises(figures.FigureIndexMissing):
            figures.recommend([_section("x", "y")])
        figures._cached.cache_clear()


class TestRanking:
    def test_scene_ranks_above_poster_on_same_match(self, fake_index: Path) -> None:
        # 图注只共享「招生」时海报才有分；共享实景词时实景必须在前
        rows = figures.recommend([_section("水下机器人", "水下机器人正在水池中测试，队员反复调试")])
        assert rows
        assert rows[0]["id"] == "f0001"
        assert rows[0]["score"] >= rows[-1]["score"]

    def test_weak_flagged_when_only_title_matches(self, fake_index: Path) -> None:
        # 「夺魁」只和来源标题重合，六张图注都对不上：这种图必须标 weak，
        # 不能混进正式推荐。阈值放低到 0.05，专门验证「弱命中」这条分支。
        rows = figures.recommend([_section("夺魁背后的故事", "三天集训，反复拆装")], min_score=0.05)
        assert len(rows) == 1
        assert rows[0]["weak"] is True

    def test_strong_match_suppresses_weak_filler(self, fake_index: Path) -> None:
        rows = figures.recommend(
            [_section("水下机器人", "水下机器人正在水池中测试，队员反复调试")],
            min_score=0.05,
        )
        assert all(row["weak"] is False for row in rows)

    def test_empty_when_nothing_matches(self, fake_index: Path) -> None:
        assert figures.recommend([_section("天气", "今天多云转晴，气温 22 度")]) == []

    def test_no_image_reused_across_sections(self, fake_index: Path) -> None:
        sections = [
            _section("水下机器人", "水下机器人正在水池中测试"),
            _section("水下机器人", "水下机器人正在水池中测试"),
        ]
        ids = [row["id"] for row in figures.recommend(sections)]
        assert len(ids) == len(set(ids))

    def test_section_index_and_heading_kept(self, fake_index: Path) -> None:
        rows = figures.recommend([_section("第一", "无关内容"), _section("水下机器人", "水下机器人正在水池中测试")])
        assert rows
        assert rows[0]["sectionIndex"] == 1
        assert rows[0]["sectionHeading"] == "水下机器人"


class TestResolve:
    def test_resolve_known_and_unknown(self, fake_index: Path) -> None:
        assert figures.resolve("f0001") is not None
        assert figures.resolve("f9999") is None

    def test_resolve_returns_none_when_file_deleted(self, fake_index: Path) -> None:
        (fake_index.parent / "某篇推文" / "f0001.png").unlink()
        assert figures.resolve("f0001") is None


class TestEndpoint:
    def test_serves_image_bytes(self, fake_index: Path) -> None:
        client = TestClient(app)
        response = client.get("/api/figure/f0001")
        assert response.status_code == 200
        assert response.content.startswith(b"\x89PNG")

    def test_unknown_id_404(self, fake_index: Path) -> None:
        client = TestClient(app)
        assert client.get("/api/figure/nope").status_code == 404

    def test_stats_endpoint(self, fake_index: Path) -> None:
        body = TestClient(app).get("/api/figures/stats").json()
        assert body["total"] == 4
        assert body["kinds"]["scene"] == 1


class TestComposeIntegration:
    def test_figures_attached_and_exported_to_markdown(self, fake_index: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from api import compose

        article = {
            "title": "水下机器人国赛夺魁",
            "lead": "导语",
            "sections": [{"heading": "水池里的三个小时", "paragraphs": [{"text": "水下机器人正在水池中测试"}]}],
            "imageSuggestions": [],
        }
        figs = compose.attach_figures(article)
        assert figs and figs[0]["url"] == "/api/figure/f0001"

        md = compose.figures_to_markdown(figs)
        assert "配图占位" in md
        assert "水下机器人" in md
        # 导出稿只给占位与图注，不嵌本地接口链接（别人打不开）
        assert "/api/figure/" not in md
        assert "《水下机器人国赛夺魁》" in md

    def test_index_missing_does_not_break_compose(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from api import compose

        monkeypatch.setattr(figures, "INDEX", tmp_path / "nope.json")
        figures._cached.cache_clear()
        assert compose.attach_figures({"sections": [{"heading": "x", "paragraphs": [{"text": "y"}]}]}) == []
        assert compose.figures_to_markdown([]) == ""
        figures._cached.cache_clear()
