import { describe, expect, it } from 'vitest';
import { readPartial } from './partialArticle';

describe('readPartial', () => {
  it('完整 JSON 解出标题、导语与分节段落', () => {
    const raw = JSON.stringify({
      title: '报到指引',
      lead: '一句话导语',
      sections: [
        { heading: '线上报到', paragraphs: [{ text: '第一段', cites: ['A1'] }] },
        { heading: '现场注册', paragraphs: [{ text: '第二段', cites: [] }] },
      ],
    });

    const partial = readPartial(raw);

    expect(partial.title).toBe('报到指引');
    expect(partial.lead).toBe('一句话导语');
    expect(partial.sections.map((s) => s.heading)).toEqual(['线上报到', '现场注册']);
    expect(partial.sections[1]?.paragraphs).toEqual(['第二段']);
  });

  it('字符串写到一半时只显示已闭合的字段', () => {
    const raw = '{"title":"报到指引","lead":"导语写到一半';

    const partial = readPartial(raw);

    expect(partial.title).toBe('报到指引');
    expect(partial.lead).toBe('');
  });

  it('正文里的转义引号能正确还原', () => {
    const raw = '{"sections":[{"heading":"标题","paragraphs":[{"text":"他说\\"开学\\"了"}]}]}';

    const partial = readPartial(raw);

    expect(partial.sections[0]?.paragraphs[0]).toBe('他说"开学"了');
  });

  it('正文里出现 heading 字样不会被当成新的一节', () => {
    const raw =
      '{"sections":[{"heading":"一","paragraphs":[{"text":"正文提到 \\"heading\\": \\"假\\" 字样"},{"text":"第二段"}]}]}';

    const partial = readPartial(raw);

    expect(partial.sections).toHaveLength(1);
    expect(partial.sections[0]?.paragraphs).toHaveLength(2);
  });

  it('模型漏写 heading 时正文仍然显示', () => {
    const raw = '{"sections":[{"paragraphs":[{"text":"孤立的一段"}]}]}';

    const partial = readPartial(raw);

    expect(partial.sections).toHaveLength(1);
    expect(partial.sections[0]?.heading).toBe('');
    expect(partial.sections[0]?.paragraphs).toEqual(['孤立的一段']);
  });

  it('空串不炸，字数按原始长度算', () => {
    expect(readPartial('')).toEqual({ title: '', lead: '', sections: [], chars: 0 });
    expect(readPartial('abc').chars).toBe(3);
  });
});
