import { describe, expect, it } from 'vitest';

import { CASES } from './cases';
import { RULES } from './content';

/**
 * 权威口径回归：媒体传讯处 2026-11-24 裁决
 * 版本 20260618 为准、QS 2027 = 第 52 位、2026.05 与 (2) 副本忽略。
 * 前端展示文案不得回潮到「待确认」或旧版本号；首页轮播也不再以校稿案例为主角。
 */
describe('权威口径 20260618 / QS 第52位', () => {
  it('规则依据全部标注 20260618，不再引用旧版 2026.05', () => {
    const manualRules = RULES.filter((r) => r.source.includes('常用表述规范手册'));
    expect(manualRules.length).toBeGreaterThan(0);
    for (const rule of manualRules) {
      expect(rule.source).toContain('20260618');
      expect(rule.source).not.toContain('2026.05');
    }
  });

  it('RANK-001 依据已裁决，不再写「不替人拍板 / 待确认」', () => {
    const rank = RULES.find((r) => r.id === 'RANK-001');
    expect(rank?.quote).toContain('第 52 位');
    expect(rank?.note).toContain('忽略');
    expect(rank?.note).not.toContain('不自行判定');
  });

  it('首页轮播按 RAG → Agent → 成稿定位组织，不再展示校稿命中案例', () => {
    expect(CASES.map((c) => c.id)).toEqual(['STAGE-01', 'STAGE-02', 'STAGE-03']);
    expect(CASES.some((c) => c.id === 'RANK-001')).toBe(false);
    expect(CASES.every((c) => c.points.length >= 3)).toBe(true);
  });

  it('末帧明确终点是可直发文章，校稿只是其中一个环节', () => {
    const last = CASES.find((c) => c.id === 'STAGE-03');
    expect(last?.phase).toContain('可直发');
    expect(last?.output).toContain('公众号文章');
    expect(last?.note).toContain('不是一份检查报告');
  });
});
