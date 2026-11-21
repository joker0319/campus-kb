import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../App';

const jsonResponse = (body: unknown): Promise<Response> =>
  Promise.resolve({
    ok: true,
    status: 200,
    json: () => Promise.resolve(body),
  } as Response);

const RULES = {
  total: 1,
  rules: [
    {
      id: 'PUNCT-001',
      category: '标点',
      severity: 'error',
      type: 'halfwidth',
      desc: '中文语境使用半角标点',
      suggestion: '改用全角标点',
      source: '常用表述规范手册｜四、标点',
      file: '常用表述规范手册',
    },
  ],
};

describe('助手页', () => {
  beforeEach(() => {
    window.location.hash = '#/assistant';
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const url =
          typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
        if (url.includes('/api/rules')) return jsonResponse(RULES);
        if (url.includes('/api/search')) {
          return jsonResponse({
            query: '于吉红',
            total: 1,
            scanned: 26,
            results: [{ file: '奠基通稿', line: 3, excerpt: '于吉红出席仪式', hits: 1 }],
          });
        }
        if (url.includes('/api/review')) {
          return jsonResponse({
            findings: [],
            counts: { total: 0, error: 0, warn: 0, info: 0 },
            ruleCount: 19,
          });
        }
        throw new Error(`unexpected url ${url}`);
      }),
    );
  });

  afterEach(() => {
    window.location.hash = '';
    vi.unstubAllGlobals();
  });

  it('渲染助手界面并展示三项可用工具', async () => {
    render(<App />);
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '有什么可以帮你？' })).toBeTruthy();
    });
    expect(screen.getByRole('link', { name: '← 返回首页' })).toBeTruthy();
    expect(
      screen.getAllByRole('button', { name: /问规范|查档案|校稿件/ }).length,
    ).toBeGreaterThanOrEqual(3);
    expect(screen.getByLabelText<HTMLInputElement>('助手输入框').disabled).toBe(false);
  });

  it('问规范：输入关键词后展示带出处的规则', async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: '有什么可以帮你？' })).toBeTruthy(),
    );

    await user.type(screen.getByLabelText('助手输入框'), '标点');
    await user.click(screen.getByRole('button', { name: '发送' }));

    await waitFor(() => {
      expect(screen.getByText(/命中 1 条规范/)).toBeTruthy();
    });
    expect(screen.getByText(/出处：常用表述规范手册/)).toBeTruthy();
    expect(screen.getByText(/建议：改用全角标点/)).toBeTruthy();
  });

  it('查档案：切换工具后检索并展示文件名与行号', async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: '有什么可以帮你？' })).toBeTruthy(),
    );

    // 底部工具条里选「查档案」
    const chips = screen.getAllByRole('button', { name: '查档案' });
    await user.click(chips[chips.length - 1]!);
    await user.type(screen.getByLabelText('助手输入框'), '于吉红');
    await user.click(screen.getByRole('button', { name: '发送' }));

    await waitFor(() => {
      expect(screen.getByText(/在 26 份档案中命中/)).toBeTruthy();
    });
    expect(screen.getByText(/奠基通稿 · 第 3 行/)).toBeTruthy();
  });

  it('校稿件：无命中时明确说明，不伪装回答', async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: '有什么可以帮你？' })).toBeTruthy(),
    );

    const chips = screen.getAllByRole('button', { name: '校稿件' });
    await user.click(chips[chips.length - 1]!);
    await user.type(screen.getByLabelText('助手输入框'), '这是一段合规正文');
    await user.click(screen.getByRole('button', { name: '发送' }));

    await waitFor(() => {
      expect(screen.getByText(/未发现问题/)).toBeTruthy();
    });
  });
});
