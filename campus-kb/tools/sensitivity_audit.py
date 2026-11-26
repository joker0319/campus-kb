#!/usr/bin/env python3
"""语料敏感信息审查（只读）：扫描 corpus 中的联系方式、证件号与内部档案。

用法：
    python tools/sensitivity_audit.py
    python tools/sensitivity_audit.py --json /tmp/sensitivity_report.json

注意：脚本只输出统计与打码样例，不输出完整号码；不修改任何语料文件。
命中不等于泄露——公开推文里的招生电话属于公开业务信息，需结合上下文判断。
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

CORPUS = Path(__file__).resolve().parents[1] / "corpus"

# 命中后需人工看上下文；正则只负责把候选捞出来
PATTERNS: dict[str, re.Pattern[str]] = {
    "手机号": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "邮箱": re.compile(r"[\w.\-+]+@[\w\-]+\.[\w.]{2,}"),
    "疑似身份证/长编号": re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
    "座机": re.compile(r"(?<!\d)0\d{2,3}-?\d{7,8}(?!\d)"),
    "长数字串(剪报ID/链接片段)": re.compile(r"(?<!\d)\d{12,19}(?!\d)"),
    "URL 分享 token": re.compile(r"[?&]share_token=[0-9a-f\-]{16,}", re.I),
}


def category(path: Path) -> str:
    if "_DOCUMENT" in path.name:
        return "internal_archive"
    if "_WX" in path.name:
        return "public_wechat"
    return "other"


def mask(value: str) -> str:
    if len(value) <= 8:
        return value[:2] + "*" * max(0, len(value) - 4) + value[-2:]
    return value[:3] + "*" * (len(value) - 6) + value[-3:]


def scan() -> dict[str, Any]:
    files = sorted(CORPUS.rglob("*.txt")) + sorted(CORPUS.glob("*.json")) + sorted(CORPUS.glob("*.md"))
    counts: Counter[tuple[str, str]] = Counter()
    samples: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    file_categories = Counter()

    for path in files:
        cat = category(path)
        file_categories[cat] += 1
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for label, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                key = (label, cat)
                counts[key] += 1
                if len(samples[key]) < 5:
                    line = text.count("\n", 0, match.start()) + 1
                    samples[key].append(
                        {
                            "file": str(path.relative_to(CORPUS)),
                            "line": line,
                            "masked": mask(match.group()),
                        }
                    )

    return {
        "scanned_files": len(files),
        "file_categories": dict(file_categories),
        "counts": {f"{label}|{cat}": n for (label, cat), n in sorted(counts.items())},
        "samples": {f"{label}|{cat}": rows for (label, cat), rows in sorted(samples.items())},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="语料敏感信息审查（只读）")
    parser.add_argument("--json", dest="json_path", help="同时写出 JSON 报告")
    args = parser.parse_args()

    report = scan()
    print(f"扫描文件：{report['scanned_files']} 个；分类：{report['file_categories']}")
    for key, n in report["counts"].items():
        print(f"\n=== {key}: {n} 处 ===")
        for row in report["samples"].get(key, []):
            print(f"  {row['file']}:{row['line']}  {row['masked']}")
    print("\n判断要点：")
    print("- _WX 公开推文中的招生电话/邮箱是主动公布的业务联系方式，非个人隐私。")
    print("- 长编号多为 Wisers 剪报 ID 或新闻 URL 片段，不是身份证/学号，需人工确认。")
    print("- _DOCUMENT 内部档案含工作方案、采购论证、行程安排，公网开放前需人工决策。")
    print("- 本脚本不修改语料；需要收紧时优先在检索层按文件类别过滤，不要直接删原文。")

    if args.json_path:
        Path(args.json_path).write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nJSON 报告：{args.json_path}")


if __name__ == "__main__":
    main()
