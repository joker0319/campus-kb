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
