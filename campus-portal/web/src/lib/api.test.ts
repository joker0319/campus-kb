import { afterEach, describe, expect, it, vi } from 'vitest';
import { postReview, reviewFile, toIssue, toSeverity } from './api';
import fixture from '../test/fixtures/review.json';

afterEach(() => vi.unstubAllGlobals());

describe('API 映射层', () => {
  it('严重度映射：error 保留，warn/info 收敛为 warning', () => {
    expect(toSeverity('error')).toBe('error');
    expect(toSeverity('warn')).toBe('warning');
    expect(toSeverity('info')).toBe('warning');
  });

  it('finding → Issue 使用后端 key，不重算；建议为空时给兜底文案', () => {
    const f = fixture.findings[0]!;
    expect(toIssue(f)).toMatchObject({ key: f.key, ruleId: f.ruleId, line: f.line });
    expect(toIssue({ ...f, suggestion: '' }).fix).toBe('以规范原文为准');
  });

  it('postReview 发送 content + mode，返回真实命中', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(fixture),
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await postReview('测试正文', 'archive');
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/review',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ content: '测试正文', mode: 'archive' }),
      }),
    );
    expect(result.issues).toHaveLength(17);
    expect(result.ruleCount).toBe(19);
    expect(result.rawCounts).toEqual({ total: 17, error: 11, warn: 6, info: 0 });
  });

  it('非 2xx 直接抛错，不返回假数据', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500 }));
    await expect(postReview('测试正文')).rejects.toThrow('校验接口返回 500');
  });

  it('reviewFile 用 FormData 上传 docx，映射提取正文、命中与 Markdown 报告', async () => {
    const body = {
      filename: '活动通知.docx',
      text: '标题\n正文\n港城大（东莞）出席。',
      findings: fixture.findings,
      counts: fixture.counts,
      ruleCount: 19,
      report: '# 稿件校验报告\n- 文件：`活动通知.docx`\n',
    };
    const fetchMock = vi.fn((_url: string, _init?: RequestInit) =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve(body),
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    const file = new File(['docx'], '活动通知.docx', {
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    });
    const result = await reviewFile(file);

    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe('/api/review-file');
    expect(init).toMatchObject({ method: 'POST' });
    expect((init?.body as FormData).get('file')).toBe(file);
    expect(result.filename).toBe(body.filename);
    expect(result.text).toBe(body.text);
    expect(result.report).toContain('稿件校验报告');
    expect(result.issues).toHaveLength(17);
    expect(result.ruleCount).toBe(19);
  });

  it('reviewFile 非 2xx 抛错，提示文件校验接口', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 400 }));
    const file = new File(['bad'], 'x.docx');
    await expect(reviewFile(file)).rejects.toThrow('文件校验接口返回 400');
  });
});
