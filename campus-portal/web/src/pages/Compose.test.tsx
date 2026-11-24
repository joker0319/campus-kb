import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Compose from './Compose';
import type { ComposeResult } from '../lib/api';

const RESULT: ComposeResult = {
  topic: '写一篇科研进展推文',
  article: {
    title: '港城莞科研新进展',
    lead: '一句话导语',
    sections: [
      {
        heading: '科研',
        paragraphs: [
          { text: '据档案记载，学校取得进展。', cites: ['A1'] },
          { text: '（素材不足，待补充）', cites: [] },
        ],
      },
    ],
    imageSuggestions: [{ after: '科研', description: '实验室照片' }],
  },
  markdown: '# 港城莞科研新进展\n据档案记载，学校取得进展。 [A1]',
  sources: [{ ref: 'A1', kind: 'wechat', text: '学校取得进展', file: 'news_WX.txt', line: 3 }],
  rules: [],
  meta: { terms: ['科研'], scanned: 50 },
  citations: {
    cited: [{ ref: 'A1', kind: 'wechat', text: '学校取得进展', file: 'news_WX.txt', line: 3 }],
    uncitedParagraphs: 0,
    invalidCites: [],
    paragraphCount: 1,
    grounded: true,
  },
  review: {
    counts: { total: 0, error: 0, warn: 0, info: 0 },
    findings: [],
  },
  model: 'deepseek-chat',
};

describe('写文章页', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        () =>
          Promise.resolve({
            ok: true,
            json: () => Promise.resolve(RESULT),
          }) as Promise<Response>,
      ),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    window.location.hash = '';
  });

  it('渲染选题输入与生成按钮', () => {
    render(<Compose />);
    expect(screen.getByLabelText('文章选题输入框')).toBeTruthy();
    expect(screen.getByRole('button', { name: '生成文章' })).toBeTruthy();
  });

  it('选题过短时生成按钮禁用', () => {
    render(<Compose />);
    const button = screen.getByRole('button', { name: '生成文章' }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
  });

  it('生成后展示结构化草稿、出处与配图建议', async () => {
    const user = userEvent.setup();
    render(<Compose />);
    await user.type(screen.getByLabelText('文章选题输入框'), '写一篇科研进展推文');
    await user.click(screen.getByRole('button', { name: '生成文章' }));

    await waitFor(() => {
      expect(screen.getByText('港城莞科研新进展')).toBeTruthy();
    });
    expect(screen.getByText('据档案记载，学校取得进展。')).toBeTruthy();
    expect(screen.getAllByText('[A1]').length).toBeGreaterThan(0);
    expect(screen.getByText('配图建议')).toBeTruthy();
    expect(screen.getByText(/全部段落有出处/)).toBeTruthy();

    const fetchMock = vi.mocked(fetch);
    const call = fetchMock.mock.calls.find(([input]) => String(input).includes('/api/compose'));
    expect(call).toBeTruthy();
    expect(JSON.parse((call![1] as RequestInit).body as string)).toEqual({
      topic: '写一篇科研进展推文',
    });
  });

  it('接口失败时显示错误，不伪造草稿', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        () =>
          Promise.resolve({
            ok: false,
            status: 503,
            json: () => Promise.resolve({ detail: '未配置 DEEPSEEK_API_KEY' }),
          }) as Promise<Response>,
      ),
    );
    const user = userEvent.setup();
    render(<Compose />);
    await user.type(screen.getByLabelText('文章选题输入框'), '写一篇科研进展推文');
    await user.click(screen.getByRole('button', { name: '生成文章' }));

    await waitFor(() => {
      expect(screen.getByRole('alert').textContent).toContain('未配置 DEEPSEEK_API_KEY');
    });
  });
});
