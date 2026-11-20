"""API 契约与回归测试。

基线来自 campus-kb 实测（README「已验证的结果」）：
- bad-draft.md  命中 17 项：错误 11 / 警告 6
- good-draft.md 命中 0 项
任何改动导致这两个数字变化，必须先确认是规则更新所致并同步 README。
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.search import load_corpus, search

KB = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def _sample(name: str) -> str:
    return (KB / "samples" / f"{name}.md").read_text(encoding="utf-8")


class TestHealth:
    def test_ok(self, client: TestClient) -> None:
        assert client.get("/api/health").json() == {"status": "ok"}


class TestRules:
    def test_19_rules(self, client: TestClient) -> None:
        r = client.get("/api/rules")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 19
        assert len(data["rules"]) == 19

    def test_every_rule_has_source(self, client: TestClient) -> None:
        for rule in client.get("/api/rules").json()["rules"]:
            assert rule["source"], f"{rule['id']} 缺出处"
            assert rule["file"], f"{rule['id']} 缺文件名"


class TestReview:
    def test_bad_draft_baseline(self, client: TestClient) -> None:
        r = client.post("/api/review", json={"content": _sample("bad-draft")})
        assert r.status_code == 200
        data = r.json()
        assert data["counts"] == {"total": 17, "error": 11, "warn": 6, "info": 0}
        assert data["ruleCount"] == 19

    def test_good_draft_zero_finding(self, client: TestClient) -> None:
        r = client.post("/api/review", json={"content": _sample("good-draft")})
        assert r.status_code == 200
        data = r.json()
        assert data["counts"]["total"] == 0
        assert data["findings"] == []

    def test_findings_sorted_by_line(self, client: TestClient) -> None:
        lines = [f["line"] for f in
                 client.post("/api/review", json={"content": _sample("bad-draft")}).json()["findings"]]
        assert lines == sorted(lines)

    def test_keys_stable_and_unique(self, client: TestClient) -> None:
        findings = client.post("/api/review",
                               json={"content": _sample("bad-draft")}).json()["findings"]
        keys = [f["key"] for f in findings]
        assert len(keys) == len(set(keys)), "key 冲突会导致前端忽略/回链串行"
        for f in findings:
            assert f["key"].startswith(f"{f['ruleId']}@{f['line']}")

    def test_same_line_multiple_hits_get_suffix(self, client: TestClient) -> None:
        # 一行里踩两条 PUNCT-003 词对：第二个命中必须拿到 -2 后缀而不是覆盖
        text = "他出生于1978/5/1，入学时间是2019/9/3。\n"
        findings = client.post("/api/review", json={"content": text}).json()["findings"]
        dates = [f for f in findings if f["ruleId"].startswith("PUNCT")]
        if len(dates) >= 2:
            assert dates[0]["key"] != dates[1]["key"]

    def test_empty_content_rejected(self, client: TestClient) -> None:
        assert client.post("/api/review", json={"content": ""}).status_code == 422

    def test_layout_config_not_in_findings(self, client: TestClient) -> None:
        # layout.json 是排版配置（0 条规则），不该出现在校验结果里
        ids = {f["ruleId"] for f in
               client.post("/api/review", json={"content": _sample("bad-draft")}).json()["findings"]}
        assert ids and all(not i.startswith("LAYOUT") for i in ids)


class TestHitField:
    """每条命中都带精确原文子串，前端据此给任意稿件标红。"""

    def test_every_finding_has_hit_in_source(self) -> None:
        from checker import load_rules, run

        text = _sample("bad-draft")
        rules, _ = load_rules()
        findings = run(text, rules)
        assert findings
        for f in findings:
            assert f["hit"], f"{f['rule_id']} 缺 hit"
            assert f["hit"] in text, f"{f['rule_id']} 的 hit 不是原文子串"

    def test_api_returns_hit(self, client: TestClient) -> None:
        findings = client.post(
            "/api/review", json={"content": _sample("bad-draft")}
        ).json()["findings"]
        assert all(f["hit"] for f in findings)


class TestModes:
    """mode=submission（默认）全量规则；archive 跳过投稿格式规则（SUB-*）。"""

    def test_default_mode_is_submission(self, client: TestClient) -> None:
        r = client.post("/api/review", json={"content": _sample("bad-draft")})
        assert r.json()["ruleCount"] == 19

    def test_archive_mode_skips_sub_rules(self, client: TestClient) -> None:
        r = client.post("/api/review",
                        json={"content": _sample("bad-draft"), "mode": "archive"})
        data = r.json()
        assert all(not f["ruleId"].startswith("SUB") for f in data["findings"])
        assert data["ruleCount"] == 15

    def test_archive_mode_keeps_content_rules(self, client: TestClient) -> None:
        ids = {f["ruleId"] for f in client.post(
            "/api/review", json={"content": _sample("bad-draft"), "mode": "archive"}
        ).json()["findings"]}
        assert "NAME-001" in ids and "PUNCT-003" in ids

    def test_invalid_mode_rejected(self, client: TestClient) -> None:
        r = client.post("/api/review",
                        json={"content": "测试内容", "mode": "chat"})
        assert r.status_code == 422


class TestPunctExemptions:
    """数字间的冒号/逗号是时间/比值/千分位，不是半角标点错误。"""

    @pytest.mark.parametrize("text", [
        "会议时间是明天上午22:00，届时请准时参加\n",
        "预计在校生规模比例约为1:1，研究生占四成\n",
        "本次投入经费约1,000万元，用于设备采购\n",
    ])
    def test_digit_punct_exempt(self, client: TestClient, text: str) -> None:
        findings = client.post("/api/review", json={"content": text}).json()["findings"]
        assert not any(f["ruleId"] == "PUNCT-001" for f in findings), text

    def test_real_halfwidth_comma_still_caught(self, client: TestClient) -> None:
        findings = client.post(
            "/api/review", json={"content": "他表示,学校将持续推动合作\n"}
        ).json()["findings"]
        assert any(f["ruleId"] == "PUNCT-001" for f in findings)


@pytest.fixture()
def corpus_root(tmp_path: Path) -> Path:
    """注入临时语料目录，绕开 load_corpus 的 lru_cache。"""
    load_corpus.cache_clear()
    (tmp_path / "a.txt").write_text(
        "第一行没有关键词\n于吉红院士出席了奠基仪式\n又是无关行，奠基仪式很隆重\n",
        encoding="utf-8",
    )
    (tmp_path / "b.txt").write_text("奠基仪式于四月举行\n", encoding="utf-8")
    yield tmp_path
    load_corpus.cache_clear()


class TestSearch:
    def test_single_term(self, corpus_root: Path) -> None:
        r = search("奠基", root=corpus_root)
        assert r["total"] == 3
        assert r["scanned"] == 2
        assert r["results"][0]["file"] == "a"  # a 命中 2 行排前，name 为 stem

    def test_multi_term_is_and(self, corpus_root: Path) -> None:
        r = search("于吉红 奠基", root=corpus_root)
        assert r["total"] == 1
        assert r["results"][0]["line"] == 2

    def test_case_insensitive(self, corpus_root: Path) -> None:
        (corpus_root / "c.txt").write_text("CityU(DG) held a ceremony\n", encoding="utf-8")
        r = search("cityu", root=corpus_root)
        assert r["total"] == 1

    def test_no_match(self, corpus_root: Path) -> None:
        r = search("不存在的词", root=corpus_root)
        assert r["total"] == 0 and r["results"] == []

    def test_empty_query(self, corpus_root: Path) -> None:
        assert search("   ", root=corpus_root)["total"] == 0

    def test_endpoint(self, client: TestClient, corpus_root: Path) -> None:
        # 端点走默认语料目录，用 monkeypatch 指向临时目录
        import api.main as m
        orig = m.corpus_search.corpus_dir
        m.corpus_search.corpus_dir = lambda: corpus_root  # type: ignore[assignment]
        try:
            r = client.get("/api/search", params={"q": "奠基"})
            assert r.status_code == 200
            assert r.json()["total"] == 3
        finally:
            m.corpus_search.corpus_dir = orig  # type: ignore[assignment]

    def test_endpoint_requires_q(self, client: TestClient) -> None:
        assert client.get("/api/search").status_code == 422
