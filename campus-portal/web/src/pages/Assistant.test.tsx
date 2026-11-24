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

const AGENT_ANSWER = {
  answer: '根据档案，奠基仪式于 2021 年 4 月 22 日举行。',
  steps: [
    {
      tool: 'search_archive',
      args: { query: '奠基' },
      result: {
        kind: 'archive',
        items: [{ file: '奠基通稿', line: 3, excerpt: '4月22日举行奠基仪式', hits: 1 }],
        total: 1,
        scanned: 26,
      },
      callId: 'call_1',
    },
    {
      tool: 'search_rules',
      args: { keyword: '校名' },
      result: {
        kind: 'rules',
        items: [{ id: 'NAME-001', desc: '首次出现用全称' }],
        total: 1,
      },
      callId: 'call_2',
    },
  ],
  model: 'deepseek-chat',
  usedTools: ['search_archive', 'search_rules'],
  truncated: false,
};

describe('助手页 Agent 模式', () => {
  beforeEach(() => {
    window.location.hash = '#/assistant';
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const url =
          typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
        if (url.includes('/api/agent')) return jsonResponse(AGENT_ANSWER);
        throw new Error(`unexpected url ${url}`);
      }),
    );
  });

  afterEach(() => {
    window.location.hash = '';
    vi.unstubAllGlobals();
  });

  it('渲染单输入框，不再有手动工具切换', async () => {
    render(<App />);
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: '今天写点什么？' })).toBeTruthy();
    });
    expect(screen.getByRole('link', { name: '← 返回首页' })).toBeTruthy();
    const input = screen.getByLabelText<HTMLInputElement>('助手输入框');
    expect(input.disabled).toBe(false);
    expect(screen.queryByRole('button', { name: '问规范' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'AI 问答' })).toBeNull();
  });

  it('提问后展示 Agent 回答、工具轨迹与依据', async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: '今天写点什么？' })).toBeTruthy(),
    );

    await user.type(screen.getByLabelText('助手输入框'), '奠基仪式是什么时候？');
    await user.click(screen.getByRole('button', { name: '发送' }));

    await waitFor(() => {
      expect(screen.getByText(/2021 年 4 月 22 日举行/)).toBeTruthy();
    });
    expect(screen.getByText('执行轨迹')).toBeTruthy();
    expect(screen.getByText('查档案')).toBeTruthy();
    expect(screen.getByText('查规范')).toBeTruthy();
    expect(screen.getByText(/奠基通稿 · 第 3 行/)).toBeTruthy();
    expect(screen.getByText(/\[NAME-001\]/)).toBeTruthy();

    const fetchMock = vi.mocked(fetch);
    const agentCall = fetchMock.mock.calls.find(([input]) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
      return url.includes('/api/agent');
    });
    expect(agentCall).toBeTruthy();
    expect(JSON.parse((agentCall![1] as RequestInit).body as string)).toEqual({
      message: '奠基仪式是什么时候？',
      history: [],
    });
  });

  it('示例提问点击后填入输入框', async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: '今天写点什么？' })).toBeTruthy(),
    );

    const suggest = screen.getByRole('button', {
      name: '帮我写一段介绍学校最新科研进展的推文',
    });
    await user.click(suggest);
    expect(screen.getByLabelText<HTMLInputElement>('助手输入框').value).toBe(
      '帮我写一段介绍学校最新科研进展的推文',
    );
  });

  it('接口失败时显示错误，不伪造回答', async () => {
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
    render(<App />);
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: '今天写点什么？' })).toBeTruthy(),
    );

    await user.type(screen.getByLabelText('助手输入框'), '校名规范');
    await user.click(screen.getByRole('button', { name: '发送' }));

    await waitFor(() => {
      expect(screen.getByText(/查询失败：未配置 DEEPSEEK_API_KEY/)).toBeTruthy();
    });
  });
});
