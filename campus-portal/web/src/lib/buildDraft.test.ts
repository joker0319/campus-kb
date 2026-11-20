import { describe, expect, it } from 'vitest';
import { buildDraft } from './buildDraft';
import { toIssue } from './api';
import fixture from '../test/fixtures/review.json';
import { DRAFT_TEXT } from '../data/content';
import type { Issue } from '../types';

const issues = fixture.findings.map(toIssue) as readonly Issue[];

describe('buildDraft', () => {
  it('真实稿件：17 条命中每条都能在正文里找到标红位置', () => {
    const draft = buildDraft(DRAFT_TEXT, issues);
    const marked = new Set(draft.flatMap((p) => p.segments.flatMap((sg) => sg.issueKeys ?? [])));
    for (const it of issues) {
      expect(marked.has(it.key), `${it.key} 未标红`).toBe(true);
    }
    expect(draft).toHaveLength(5); // 行 1/3/5/7/9，空行跳过但行号保留
    expect(draft.map((p) => p.line)).toEqual([1, 3, 5, 7, 9]);
  });

  it('逐字还原正文：切分后拼回来与原文非空行完全一致', () => {
    const draft = buildDraft(DRAFT_TEXT, issues);
    const nonEmpty = DRAFT_TEXT.split('\n').filter((l) => l.trim());
    const rebuilt = draft.map((p) => p.segments.map((sg) => sg.text).join(''));
    expect(rebuilt).toEqual(nonEmpty);
  });

  it('同一命中文本的多条规则合并到同一标红片段', () => {
    const draft = buildDraft(DRAFT_TEXT, issues);
    const titleSeg = draft[0]!.segments.find((sg) => sg.issueKeys?.length === 3);
    expect(titleSeg).toBeDefined();
    expect(titleSeg!.issueKeys).toEqual(['SUB-001@1', 'SUB-002@1', 'SUB-003@1']);
  });

  it('全新稿件：按新命中的 hit 标红，与内置样例无关', () => {
    const text = '【媒体传讯处】测试稿件\n通知动态\n2026/5/1，港城大（东莞）校长张三出席。\n';
    const custom: Issue[] = [
      {
        key: 'PUNCT-003@3',
        ruleId: 'PUNCT-003',
        severity: 'warning',
        line: 3,
        message: '日期格式',
        fix: '2026年5月1日',
        hit: '2026/5/1',
      },
      {
        key: 'NAME-001@3',
        ruleId: 'NAME-001',
        severity: 'error',
        line: 3,
        message: '首次用全称',
        fix: '香港城市大学（东莞）',
        hit: '港城大（东莞）',
      },
    ];
    const draft = buildDraft(text, custom);
    expect(draft.map((p) => p.line)).toEqual([1, 2, 3]); // 第 2 行「通知动态」非空，保留
    const hitSegs = draft[2]!.segments.filter((sg) => sg.issueKeys);
    expect(hitSegs.map((sg) => sg.text)).toEqual(['2026/5/1', '港城大（东莞）']);
    expect(hitSegs.map((sg) => sg.issueKeys?.[0])).toEqual(['PUNCT-003@3', 'NAME-001@3']);
  });

  it('行级规则（整行 hit）也能标红', () => {
    const text = '这是一篇没有标题格式的稿件\n';
    const one: Issue[] = [
      {
        key: 'SUB-001@1',
        ruleId: 'SUB-001',
        severity: 'error',
        line: 1,
        message: '标题格式',
        fix: '【部门】标题',
        hit: '这是一篇没有标题格式的稿件',
      },
    ];
    const draft = buildDraft(text, one);
    expect(draft[0]!.segments[0]!.issueKeys).toEqual(['SUB-001@1']);
  });
});
