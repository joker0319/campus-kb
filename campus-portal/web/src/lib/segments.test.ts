import { describe, expect, it } from 'vitest';
import { segments } from './segments';

describe('segments', () => {
  it('无命中时返回整段', () => {
    expect(segments('一段正文', [])).toEqual([{ t: '一段正文', hit: false }]);
  });

  it('空文本返回空数组', () => {
    expect(segments('', ['a'])).toEqual([]);
  });

  it('单处命中切成两段', () => {
    expect(segments('港城大（东莞）举办', ['港城大（东莞）'])).toEqual([
      { t: '港城大（东莞）', hit: true },
      { t: '举办', hit: false },
    ]);
  });

  it('多处命中保持原文顺序', () => {
    expect(segments('第63位与52rd', ['第63位', '52rd'])).toEqual([
      { t: '第63位', hit: true },
      { t: '与', hit: false },
      { t: '52rd', hit: true },
    ]);
  });

  it('拼回后与原文逐字一致（不丢字、不改字）', () => {
    const text = '在2027年QS世界大学排名位列第63位，在QS 2027排名中位列52rd。';
    const out = segments(text, ['第63位', '52rd']);
    expect(out.map((g) => g.t).join('')).toBe(text);
  });

  it('正则元字符按字面量处理，不当作模式', () => {
    expect(segments('a(b)c', ['(b)'])[1]).toEqual({ t: '(b)', hit: true });
    expect(() => segments('价格 3.5 元', ['3.5'])).not.toThrow();
  });
});
