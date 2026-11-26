import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from '../App';

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

const frame = (event: unknown) => `data: ${JSON.stringify(event)}\n\n`;

/** 一次给齐所有帧的假后端，用于非流式的常规断言。 */
const agentFrames = (payload = AGENT_ANSWER): string => {
  const cut = Math.floor(payload.answer.length / 2);
  return (
    frame({ type: 'meta', model: payload.model }) +
    payload.steps.map((s) => frame({ type: 'step', step: s })).join('') +
    frame({ type: 'delta', text: payload.answer.slice(0, cut) }) +
    frame({ type: 'delta', text: payload.answer.slice(cut) }) +
    frame({ type: 'done', result: payload })
  );
};

/** 手动推帧的假后端，用来卡在"只写了半句"检查中间态。 */
function controlledStream() {
  const encoder = new TextEncoder();
  let push: (f: string) => void = () => {};
  let close: () => void = () => {};
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      push = (f) => controller.enqueue(encoder.encode(f));
      close = () => controller.close();
    },
  });
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(new Response(body, { status: 200 }))),
  );
  return { push, close };
}

describe('助手页 Agent 模式', () => {
  beforeEach(() => {
    window.location.hash = '#/assistant';
    // 会话与回合会落 localStorage，每个用例必须从空对话开始
    localStorage.clear();
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const url =
          typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
        if (url.includes('/api/agent/stream')) {
          return Promise.resolve(
            new Response(agentFrames(), {
              status: 200,
              headers: { 'Content-Type': 'text/event-stream' },
            }),
          );
        }
        if (url.includes('/api/agent/memory/')) {
          return Promise.resolve(new Response('{"ok":true}', { status: 200 }));
        }
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
      return url.includes('/api/agent/stream');
    });
    expect(agentCall).toBeTruthy();
    const body = JSON.parse((agentCall![1] as RequestInit).body as string) as {
      message: string;
      history: readonly unknown[];
      sessionId: string;
    };
    expect(body.message).toBe('奠基仪式是什么时候？');
    expect(body.history).toEqual([]);
    expect(body.sessionId).toMatch(/^s-[a-z0-9]+-[a-z0-9]+$/);
  });

  it('流式作答：轨迹先到，回答按增量逐字出现', async () => {
    const { push, close } = controlledStream();
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: '今天写点什么？' })).toBeTruthy(),
    );

    await user.type(screen.getByLabelText('助手输入框'), '奠基仪式是什么时候？');
    await user.click(screen.getByRole('button', { name: '发送' }));
    expect(screen.getByText('正在判断该用哪个工具…')).toBeTruthy();

    await act(async () => {
      push(frame({ type: 'meta', model: 'deepseek-chat' }));
      push(frame({ type: 'step', step: AGENT_ANSWER.steps[0] }));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    await waitFor(() => expect(screen.getByText('查档案')).toBeTruthy());
    // 回答还没开始，不该提前出现成品文本
    expect(screen.queryByText(/2021 年 4 月 22 日举行/)).toBeNull();

    await act(async () => {
      push(frame({ type: 'delta', text: '根据档案，' }));
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    await waitFor(() => expect(screen.getByText(/根据档案，/)).toBeTruthy());
    expect(screen.queryByText(/2021 年 4 月 22 日举行/)).toBeNull();

    await act(async () => {
      push(frame({ type: 'delta', text: '奠基仪式于 2021 年 4 月 22 日举行。' }));
      push(frame({ type: 'done', result: AGENT_ANSWER }));
      close();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    await waitFor(() => {
      expect(screen.getByText(/2021 年 4 月 22 日举行/)).toBeTruthy();
    });
    // done 后流式光标撤掉，轨迹按完整结果重绘
    expect(document.querySelector('[class*="streamCursor"]')).toBeNull();
    expect(screen.getByText('查规范')).toBeTruthy();
  });

  it('流里的 error 事件转成页面报错', async () => {
    const { push, close } = controlledStream();
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: '今天写点什么？' })).toBeTruthy(),
    );

    await user.type(screen.getByLabelText('助手输入框'), '校名规范');
    await user.click(screen.getByRole('button', { name: '发送' }));

    await act(async () => {
      push(frame({ type: 'meta', model: 'deepseek-chat' }));
      push(frame({ type: 'error', message: '上游不可用' }));
      close();
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    await waitFor(() => {
      expect(screen.getByText(/查询失败：上游不可用/)).toBeTruthy();
    });
  });

  it('发出后滚到新回合顶部，而不是把视口拽到底部', async () => {
    const scrollSpy = vi.mocked(Element.prototype.scrollIntoView);
    scrollSpy.mockClear();
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: '今天写点什么？' })).toBeTruthy(),
    );

    await user.type(screen.getByLabelText('助手输入框'), '奠基仪式是什么时候？');
    await user.click(screen.getByRole('button', { name: '发送' }));

    await waitFor(() => expect(scrollSpy).toHaveBeenCalled());
    // 必须从「用户消息所在的新回合」顶部开始往下读，不允许 block:'end' 置底
    expect(scrollSpy).toHaveBeenCalledWith({ block: 'start' });
    expect(scrollSpy).not.toHaveBeenCalledWith({ block: 'end' });
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

  it('刷新后从本地记忆恢复上一轮对话', async () => {
    localStorage.setItem('campus-agent-session', 's-restored-1');
    localStorage.setItem(
      'campus-agent-turns',
      JSON.stringify([{ id: 1, query: '奠基仪式是什么时候？', result: AGENT_ANSWER }]),
    );

    render(<App />);
    await waitFor(() => expect(screen.getByText(AGENT_ANSWER.answer)).toBeTruthy());
    expect(screen.queryByRole('heading', { name: '今天写点什么？' })).toBeNull();
    expect(screen.getByText('奠基仪式是什么时候？')).toBeTruthy();
  });

  it('新对话清空本地回合并清理服务端会话', async () => {
    localStorage.setItem(
      'campus-agent-turns',
      JSON.stringify([{ id: 1, query: '旧问题', result: AGENT_ANSWER }]),
    );
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(screen.getByText(AGENT_ANSWER.answer)).toBeTruthy());

    const button = screen.getByRole('button', { name: '新对话' }) as HTMLButtonElement;
    expect(button.disabled).toBe(false);
    await user.click(button);

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: '今天写点什么？' })).toBeTruthy(),
    );
    // 清空后 effect 会重写空数组，关键是本地不再残留任何回合
    expect(JSON.parse(localStorage.getItem('campus-agent-turns') ?? '[]')).toEqual([]);
    const deleted = vi
      .mocked(fetch)
      .mock.calls.some(
        ([url, init]) =>
          String(url).includes('/api/agent/memory/') &&
          (init as RequestInit | undefined)?.method === 'DELETE',
      );
    expect(deleted).toBe(true);
  });
});
