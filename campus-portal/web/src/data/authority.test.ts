import { describe, expect, it } from 'vitest';

import { CASES } from './cases';
import { RULES } from './content';

/**
 * 权威口径回归：媒体传讯处 2026-11-24 裁决
 * 版本 20260618 为准、QS 2027 = 第 52 位、2026.05 与 (2) 副本忽略。
 * 前端展示文案不得回潮到「待确认」或旧版本号。
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

  it('首页案例的改法指向权威值', () => {
    const rank = CASES.find((c) => c.id === 'RANK-001');
    expect(rank?.after).toContain('第52位');
    expect(rank?.why).toContain('20260618');
  });

  it('故意造错的演示稿仍保留 63 / 52rd 作为负例', () => {
    const rank = CASES.find((c) => c.id === 'RANK-001');
    expect(rank?.before).toContain('第63位');
    expect(rank?.hits).toEqual(['第63位', '52rd']);
  });
});
