import { describe, expect, it } from 'vitest';
import {
  answerFromArchive,
  answerFromChat,
  answerFromReview,
  answerFromRules,
  TOOLS,
} from './assistantTools';
import type { ArchiveResult, ChatResult, ReviewResult, RulesResult } from './api';

const rules: RulesResult = {
  total: 2,
  rules: [
    {
      id: 'PUNCT-001',
      category: '标点',
      severity: 'error',
      type: 'halfwidth',
      desc: '中文语境使用半角标点',
      suggestion: '改用全角标点',
      source: '手册｜四、标点',
      file: '手册',
    },
    {
      id: 'ENG-001',
      category: '英文',
      severity: 'error',
      type: 'ordinal',
      desc: '序数词后缀须匹配',
      suggestion: '1st/2nd/3rd',
      source: '手册｜三、英文',
      file: '手册',
    },
  ],
};

describe('assistantTools 回答映射', () => {
  it('工具清单包含 AI 问答', () => {
    expect(TOOLS.map((t) => t.kind)).toEqual(['rules', 'search', 'review', 'chat']);
  });

  it('AI 问答：回答正文保留，来源逐条列出并标记 generated', () => {
    const data: ChatResult = {
      answer: '根据 [S1]，首次出现应使用全称。',
      sources: [
        { ref: 'S1', kind: 'rule', title: 'NAME-001', detail: '校名首次出现用全称' },
        { ref: 'A1', kind: 'archive', title: '奠基通稿', detail: '香港城市大学（东莞）…' },
      ],
      model: 'deepseek-chat',
    };
    const a = answerFromChat(data);
    expect(a.tool).toBe('chat');
    expect(a.generated).toBe(true);
    expect(a.model).toBe('deepseek-chat');
    expect(a.summary).toBe(data.answer);
    expect(a.items).toHaveLength(2);
    expect(a.items[0]!.title).toContain('S1');
    expect(a.items[1]!.meta).toBe('档案片段');
  });

  it('问规范：按关键词筛选，逐条给出处', () => {
    const a = answerFromRules('标点', rules);
    expect(a.summary).toContain('命中 1 条');
    expect(a.items).toHaveLength(1);
    expect(a.items[0]!.meta).toContain('出处：手册｜四、标点');
    expect(a.items[0]!.detail).toContain('改用全角标点');
  });

  it('问规范：查不到时明确说不知道，不臆测', () => {
    const a = answerFromRules('不存在的规范', rules);
    expect(a.items).toHaveLength(0);
    expect(a.summary).toContain('未找到');
    expect(a.summary).toContain('不做臆测');
  });

  it('问规范：空关键词给出提示', () => {
    expect(answerFromRules('  ', rules).items).toHaveLength(0);
    expect(answerFromRules('', rules).summary).toContain('请输入关键词');
  });

  it('查档案：命中带文件名与行号', () => {
    const data: ArchiveResult = {
      query: '于吉红',
      total: 1,
      scanned: 26,
      results: [{ file: '奠基通稿', line: 3, excerpt: '于吉红出席', hits: 2 }],
    };
    const a = answerFromArchive('于吉红', data);
    expect(a.summary).toContain('26 份');
    expect(a.items[0]!.meta).toContain('奠基通稿');
    expect(a.items[0]!.meta).toContain('第 3 行');
  });

  it('查档案：未命中时说明扫描数量', () => {
    const a = answerFromArchive('xyz', {
      query: 'xyz',
      total: 0,
      scanned: 26,
      results: [],
    });
    expect(a.items).toHaveLength(0);
    expect(a.summary).toContain('26 份');
    expect(a.summary).toContain('未找到');
  });

  it('校稿件：命中逐条给出规则号、行号与改法', () => {
    const data: ReviewResult = {
      issues: [
        {
          key: 'PUNCT-001@2',
          ruleId: 'PUNCT-001',
          severity: 'error',
          line: 2,
          message: '中文语境使用半角标点',
          fix: '改用全角标点',
          hit: ',',
        },
      ],
      rawCounts: { total: 1, error: 1, warn: 0, info: 0 },
      ruleCount: 19,
      durationMs: 5,
    };
    const a = answerFromReview(data);
    expect(a.summary).toContain('发现 1 处');
    expect(a.items[0]!.meta).toContain('[PUNCT-001]');
    expect(a.items[0]!.meta).toContain('第 2 行');
    expect(a.items[0]!.detail).toContain('改用全角标点');
  });

  it('校稿件：无命中时说明所用规则数', () => {
    const a = answerFromReview({
      issues: [],
      rawCounts: { total: 0, error: 0, warn: 0, info: 0 },
      ruleCount: 19,
      durationMs: 5,
    });
    expect(a.items).toHaveLength(0);
    expect(a.summary).toContain('19 条规则');
    expect(a.summary).toContain('未发现问题');
  });
});
