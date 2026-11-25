#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
规则引擎（项目的一个功能）—— 把《常用表述规范手册》《投稿须知》变成可执行校验。
项目主线是 RAG 知识库 + Agent 内容助手 → 生成可用公众号文章；本模块负责其中的规范校验。

用法：
  python3 checker.py samples/bad-draft.md
  python3 checker.py samples/bad-draft.md --md reports/report.md
  python3 checker.py samples/bad-draft.md --json

规则来自 rules/*.json，新增规则只需改 JSON，不用动代码。
"""
import argparse
import json
import re
import sys
from datetime import datetime
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RULES_DIR = ROOT / "rules"
CN = "\u4e00-\u9fa5"

SEV_RANK = {"error": 0, "warn": 1, "info": 2}
SEV_LABEL = {"error": "错误", "warn": "警告", "info": "提示"}
C = {"error": "\033[31m", "warn": "\033[33m", "info": "\033[36m",
     "dim": "\033[2m", "bold": "\033[1m", "off": "\033[0m"}


@lru_cache(maxsize=1)
def load_authority():
    """媒体传讯处口径裁决的单一事实源（authority.json）。

    规则引擎、Agent 系统提示、文章生成都从这里取权威版本与权威数值，
    避免同一个口径在多处硬编码后再次漂移。文件缺失时返回空字典，
    校验链不会因此中断。
    """
    try:
        return json.loads((ROOT / "authority.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def authority_brief():
    """给 Agent / 文章生成用的一句话口径摘要。"""
    data = load_authority()
    if not data:
        return ""
    version = data.get("manual", {}).get("canonical_version", "")
    ignored = "、".join(data.get("manual", {}).get("ignored_copies", []))
    facts = []
    for key, item in data.get("facts", {}).items():
        facts.append("%s权威值为%s" % (item.get("label", key), item.get("canonical_text", item.get("value"))))
    parts = []
    if version:
        parts.append("规范版本以 %s 为准" % version)
    if ignored:
        parts.append("%s一律忽略" % ignored)
    if facts:
        parts.append("；".join(facts))
    return "；".join(parts) + "。"


def mk(rule, line_no, excerpt, message, suggestion=None, hit=None):
    return {
        "rule_id": rule["id"],
        "category": rule["category"],
        "severity": rule["severity"],
        "line": line_no,
        "message": message,
        "excerpt": excerpt,
        "suggestion": suggestion if suggestion is not None else rule.get("suggestion", ""),
        "hit": hit or "",
    }


def line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def frag(text, start, end, pad=16):
    ls = text.rfind("\n", 0, start) + 1
    le = text.find("\n", end)
    if le == -1:
        le = len(text)
    s, e = max(ls, start - pad), min(le, end + pad)
    out = text[s:e].strip()
    return ("…" if s > ls else "") + out + ("…" if e < le else "")


# ---------------- handlers ----------------

def h_first_mention_fullname(rule, text):
    p = rule["params"]
    cands = []
    for w in p["full"]:
        for m in re.finditer(re.escape(w), text):
            cands.append((m.start(), m.end(), "full", w))
    for w in p["alias"]:
        for m in re.finditer(re.escape(w), text):
            cands.append((m.start(), m.end(), "alias", w))
    if not cands:
        return []
    cands.sort()
    st, en, kind, w = cands[0]
    if kind == "full":
        return []
    return [mk(rule, line_of(text, st), frag(text, st, en),
               "稿件首次出现校名即使用简称「%s」" % w, hit=w)]


def h_fullwidth_paren(rule, text):
    out = []
    for m in re.finditer(r"\(([^)\n]{0,14})\)", text):
        if m.start() > 0 and text[m.start() - 1] == "]":
            continue
        if not re.search("[%s]" % CN, m.group(1)):
            continue
        out.append(mk(rule, line_of(text, m.start()), frag(text, m.start(), m.end()),
                      "中文内容使用了半角括号「%s」" % m.group(0), hit=m.group(0)))
    return out


def h_halfwidth_paren_space(rule, text):
    out = []
    anchor = rule["params"]["anchor"]
    for m in re.finditer(re.escape(anchor) + r"\(", text):
        out.append(mk(rule, line_of(text, m.start()), frag(text, m.start(), m.end()),
                      "英文校名括号前缺一个半角空格", hit=anchor + "("))
    return out


def h_forbid_pattern(rule, text):
    out = []
    msg = rule["params"].get("message") or rule["desc"]
    for m in re.finditer(rule["params"]["pattern"], text):
        out.append(mk(rule, line_of(text, m.start()), frag(text, m.start(), m.end()), msg, hit=m.group(0)))
    return out


def h_dictionary(rule, text):
    out = []
    for item in rule["params"]["pairs"]:
        pat = re.compile(item["wrong"] if item.get("regex") else re.escape(item["wrong"]))
        for m in pat.finditer(text):
            lo, hi = max(0, m.start() - 25), min(len(text), m.end() + 25)
            if item.get("exclude") and re.search(item["exclude"], text[lo:hi]):
                continue
            note = item.get("note") or ""
            msg = "「%s」应写作「%s」" % (m.group(0), item["right"])
            if note:
                msg += "（%s）" % note
            out.append(mk(rule, line_of(text, m.start()), frag(text, m.start(), m.end()), msg, hit=m.group(0)))
    return out


def h_must_near(rule, text):
    out = []
    win = rule["params"].get("window", 45)
    for item in rule["params"]["people"]:
        for m in re.finditer(re.escape(item["name"]), text):
            ctx = text[max(0, m.start() - win): m.end() + win]
            if any(k in ctx for k in item["must_near"]):
                continue
            out.append(mk(rule, line_of(text, m.start()), frag(text, m.start(), m.end()),
                          "「%s」附近未见规范职务表述（应含 %s）"
                          % (item["name"], " / ".join(item["must_near"])), hit=item["name"]))
    return out


def exclude_spans(pattern, text):
    """专有名词豁免区间：落在 exclude 命中区间内的术语不再判定。

    用于「港澳台侨联招」这类全称里含禁用写法、但改了就错的专名。
    """
    if not pattern:
        return []
    return [(m.start(), m.end()) for m in re.finditer(pattern, text)]


def h_require_context(rule, text):
    out = []
    for item in rule["params"]["terms"]:
        skip = exclude_spans(item.get("exclude"), text)
        for m in re.finditer(re.escape(item["term"]), text):
            if any(s <= m.start() and m.end() <= e for s, e in skip):
                continue
            scope = item.get("scope") or rule["params"].get("scope", "window")
            if scope == "document":
                ctx = text
            else:
                w = rule["params"].get("window", 8)
                ctx = text[max(0, m.start() - w): m.end() + w]
            if any(k in ctx for k in item["require"]):
                continue
            out.append(mk(rule, line_of(text, m.start()), frag(text, m.start(), m.end()),
                          "「%s」须明确为 %s" % (item["term"], " / ".join(item["require"])), hit=m.group(0)))
    return out


def h_halfwidth_punct_in_cn(rule, text):
    out = []
    trans = {",": "，", ";": "；", ":": "：", "?": "？", "!": "！"}
    for i, line in enumerate(text.split("\n"), 1):
        if len(re.findall("[%s]" % CN, line)) < 4:
            continue
        hits = []
        for m in re.finditer(r"[,;:?!]", line):
            # 数字之间的冒号/逗号是时间（22:00）、比值（1:1）、千分位（1,000），豁免
            before = line[m.start() - 1] if m.start() > 0 else ""
            after = line[m.end()] if m.end() < len(line) else ""
            if before.isdigit() and after.isdigit():
                continue
            lo, hi = max(0, m.start() - 3), min(len(line), m.end() + 3)
            if re.search("[%s]" % CN, line[lo:hi]):
                hits.append(m.group(0))
        if not hits:
            continue
        uniq = sorted(set(hits))
        out.append(mk(rule, i, line.strip()[:70],
                      "中文语境使用了半角标点 %s（共 %d 处）"
                      % ("、".join("「%s」" % c for c in uniq), len(hits)),
                      "改用全角 " + " ".join("「%s」" % trans[c] for c in uniq), hit=uniq[0]))
    return out


def h_no_space_number_unit(rule, text):
    out = []
    units = "|".join(re.escape(u) for u in rule["params"]["units"])
    for m in re.finditer(r"\d+\s+(?:%s)" % units, text):
        compact = re.sub(r"\s+", "", m.group(0))
        out.append(mk(rule, line_of(text, m.start()), frag(text, m.start(), m.end()),
                      "数字与单位之间不应有空格「%s」" % m.group(0),
                      "改为「%s」" % compact, hit=m.group(0)))
    return out


def h_date_format(rule, text):
    out = []
    for m in re.finditer(r"(\d{4})[/.](\d{1,2})[/.](\d{1,2})", text):
        y, mo, d = m.group(1), int(m.group(2)), int(m.group(3))
        out.append(mk(rule, line_of(text, m.start()), frag(text, m.start(), m.end()),
                      "日期「%s」不符合中文格式" % m.group(0),
                      "%s年%d月%d日" % (y, mo, d), hit=m.group(0)))
    return out


def h_ordinal_suffix(rule, text):
    out = []
    for m in re.finditer(r"(?<![A-Za-z0-9])(\d+)(st|nd|rd|th)(?![A-Za-z0-9])", text):
        n, s = int(m.group(1)), m.group(2)
        if 11 <= n % 100 <= 13:
            correct = "th"
        else:
            correct = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
        if correct != s:
            out.append(mk(rule, line_of(text, m.start()), frag(text, m.start(), m.end()),
                          "英文序数词错误「%s」" % m.group(0),
                          "应为 %d%s" % (n, correct), hit=m.group(0)))
    return out


def h_title_format(rule, text):
    for i, line in enumerate(text.split("\n"), 1):
        s = line.strip()
        if not s:
            continue
        if re.match(r"^【[^】]+】", s):
            return []
        return [mk(rule, i, s[:70], "标题未按「【投稿部门】投稿内容」格式填写", hit=s)]
    return []


def h_bilingual_flag(rule, text):
    cn = len(re.findall("[%s]" % CN, text))
    en = len(re.findall(r"[A-Za-z]", text))
    title = text.strip().split("\n")[0]
    if cn > 50 and en < cn * 0.1 and "[Chinese]" not in text:
        return [mk(rule, 1, title[:60],
                   "仅提交中文内容，但英文标题未标注 [Chinese]", hit=title)]
    return []


def h_category_required(rule, text):
    cats = rule["params"]["categories"]
    if any(c in text for c in cats):
        return []
    title = text.strip().split("\n")[0]
    return [mk(rule, 1, title[:60],
               "未声明内容分类，投稿须勾选以下之一：%s" % " / ".join(cats), hit=title)]


def h_rank_conflict(rule, text):
    year = rule["params"]["year"]
    # 权威值优先取单一事实源 authority.json，规则自带值仅作兜底
    auth = load_authority().get("facts", {}).get(
        rule["params"].get("authority_key", ""), {}
    )
    canonical = auth.get("value", rule["params"].get("authoritative"))
    # 只认「排名位次」写法：第52位 / 52nd / 位列52名。
    # 旧模式抓任意 1-3 位数，会把「排名于今年6月发布」里的月份当成排名值，
    # 和真正的第52位冲突后误报 RANK-001。
    rank = r"(?:第\s*)?(\d{1,3})\s*(?:位|名|(?:st|nd|rd|th)\b)"
    pats = [
        r"QS[^\n。；]{0,35}?%s[^\n。；]{0,18}?" % year + rank,
        r"%s[^\n。；]{0,35}?QS[^\n。；]{0,18}?" % year + rank,
    ]
    hits = []
    for p in pats:
        for m in re.finditer(p, text):
            v = int(m.group(1))
            if 1 <= v <= 300:
                hits.append((m.start(), v))
    vals = sorted({v for _, v in hits})
    if not vals:
        return []
    # 两种情况合并为一条命中：① 文内多个数值冲突；② 单一数值但偏离权威口径
    # （合并且只在有问题时返回，保证坏样例基线命中数不变）
    conflict = len(vals) > 1
    deviates = canonical is not None and any(v != canonical for v in vals)
    if not (conflict or deviates):
        return []
    pos = hits[0][0]
    if conflict:
        msg = "文内 QS %s 排名出现多个不同数值 %s" % (year, vals)
    else:
        msg = "文内 QS %s 排名记为第 %s 位" % (year, vals[0])
    if deviates:
        msg += "；与权威口径第 %s 位不符，须更正" % canonical
    return [mk(rule, line_of(text, pos), frag(text, pos, pos + 12),
               msg, hit=str(hits[0][1]))]


HANDLERS = {
    "first_mention_fullname": h_first_mention_fullname,
    "fullwidth_paren": h_fullwidth_paren,
    "halfwidth_paren_space": h_halfwidth_paren_space,
    "forbid_pattern": h_forbid_pattern,
    "dictionary": h_dictionary,
    "must_near": h_must_near,
    "require_context": h_require_context,
    "halfwidth_punct_in_cn": h_halfwidth_punct_in_cn,
    "no_space_number_unit": h_no_space_number_unit,
    "date_format": h_date_format,
    "ordinal_suffix": h_ordinal_suffix,
    "title_format": h_title_format,
    "bilingual_flag": h_bilingual_flag,
    "category_required": h_category_required,
    "rank_conflict": h_rank_conflict,
}


def load_rules():
    rules, skipped = [], []
    for p in sorted(RULES_DIR.glob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        # 文件级 context 标记适用场景：submission.json 只在投稿校验时生效
        ctx = data.get("context")
        for r in data.get("rules", []):
            if r.get("type") not in HANDLERS:
                skipped.append(r["id"])
                continue
            if ctx:
                r["context"] = ctx
            rules.append(r)
    return rules, skipped


def run(text, rules, mode="submission"):
    """mode: submission=投稿校验（全量规则）；archive=档案检索（跳过投稿格式规则）"""
    findings = []
    for r in rules:
        if r.get("context") and mode != "submission":
            continue
        findings.extend(HANDLERS[r["type"]](r, text))
    findings.sort(key=lambda f: (f["line"], SEV_RANK[f["severity"]], f["rule_id"]))
    return findings


def print_console(path, findings, rule_count):
    counts = {k: sum(1 for f in findings if f["severity"] == k) for k in SEV_LABEL}
    print()
    print("%s投稿质量门%s  %s" % (C["bold"], C["off"], path.name))
    print("%s规则 %d 条 · 命中 %d 项（错误 %d / 警告 %d / 提示 %d）%s"
          % (C["dim"], rule_count, len(findings),
             counts["error"], counts["warn"], counts["info"], C["off"]))
    print("-" * 72)
    if not findings:
        print("  未发现问题\n")
        return
    for f in findings:
        print("%s%s%s 第%d行  %s[%s]%s %s"
              % (C[f["severity"]], "[" + SEV_LABEL[f["severity"]] + "]", C["off"],
                 f["line"], C["dim"], f["rule_id"], C["off"], f["message"]))
        print("%s    原文：%s%s" % (C["dim"], f["excerpt"], C["off"]))
        if f["suggestion"]:
            print("%s    建议：%s%s" % (C["dim"], f["suggestion"], C["off"]))
        print()
    print("-" * 72)
    print("%s结论：%s%s" % (C["bold"],
          "可放行" if counts["error"] == 0 else "需修改后重新提交", C["off"]))
    print()


def to_markdown(path, findings, rule_count):
    counts = {k: sum(1 for f in findings if f["severity"] == k) for k in SEV_LABEL}
    lines = []
    lines.append("# 稿件校验报告")
    lines.append("")
    lines.append("- 文件：`%s`" % path.name)
    lines.append("- 生成时间：%s" % datetime.now().strftime("%Y-%m-%d %H:%M"))
    lines.append("- 生效规则：%d 条" % rule_count)
    lines.append("- 结论：**%s**" % ("可放行" if counts["error"] == 0 else "需修改后重新提交"))
    lines.append("")
    lines.append("| 级别 | 数量 |")
    lines.append("| --- | --- |")
    for k in ["error", "warn", "info"]:
        lines.append("| %s | %d |" % (SEV_LABEL[k], counts[k]))
    lines.append("")
    lines.append("## 问题清单")
    lines.append("")
    if not findings:
        lines.append("未发现问题。")
        lines.append("")
    else:
        lines.append("| 行 | 级别 | 规则 | 问题 | 原文 | 建议 |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for f in findings:
            lines.append("| %d | %s | %s | %s | `%s` | %s |"
                         % (f["line"], SEV_LABEL[f["severity"]], f["rule_id"],
                            f["message"].replace("|", "\\|"),
                            f["excerpt"].replace("|", "\\|"),
                            f["suggestion"].replace("|", "\\|")))
        lines.append("")
    lines.append("## 覆盖的规范来源")
    lines.append("")
    for p in sorted(RULES_DIR.glob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        n = len(data.get("rules", []))
        if n:
            lines.append("- %s（%d 条）" % (data.get("source", p.stem), n))
    lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--md")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--mode", choices=["submission", "archive"], default="submission",
                    help="submission=投稿校验（默认）；archive=档案检索（跳过投稿格式规则）")
    args = ap.parse_args()

    path = Path(args.file)
    text = path.read_text(encoding="utf-8")
    rules, skipped = load_rules()
    if skipped:
        print("跳过未实现规则：%s" % ", ".join(skipped), file=sys.stderr)
    findings = run(text, rules, mode=args.mode)
    applied = len(rules) - sum(1 for r in rules if r.get("context"))

    if args.json:
        print(json.dumps({"file": str(path), "findings": findings,
                          "rule_count": applied, "mode": args.mode},
                         ensure_ascii=False, indent=2))
    else:
        print_console(path, findings, applied)

    if args.md:
        out = Path(args.md)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(to_markdown(path, findings, applied), encoding="utf-8")
        print("报告已写入 %s" % out)

    return 1 if any(f["severity"] == "error" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
