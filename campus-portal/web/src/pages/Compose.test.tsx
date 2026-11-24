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

const REVISED: ComposeResult = {
  ...RESULT,
  article: { ...RESULT.article, title: '科研新突破' },
  markdown: '# 科研新突破',
};

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function urlOf(input: RequestInfo | URL): string {
  if (typeof input === 'string') return input;
  return input instanceof URL ? input.href : input.url;
}

/** 取出请求体并解析；非字符串体直接返回 null */
function bodyOf(init: RequestInit | undefined): unknown {
  const raw = init?.body;
  return typeof raw === 'string' ? (JSON.parse(raw) as unknown) : null;
}

/** 按路径分流：/api/compose/revise 返回改后稿，其余返回初稿。 */
function mockByUrl() {
  const fetchMock = vi.fn((input: RequestInfo | URL, _init?: RequestInit) => {
    const payload = urlOf(input).includes('/revise') ? REVISED : RESULT;
    return Promise.resolve(jsonResponse(payload));
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

describe('写文章页', () => {
  beforeEach(() => {
    window.localStorage.clear();
    mockByUrl();
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
    const button = screen.getByRole<HTMLButtonElement>('button', { name: '生成文章' });
    expect(button.disabled).toBe(true);
  });

  it('生成后展示结构化草稿、出处与配图建议', async () => {
    const fetchMock = vi.mocked(fetch);
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

    const call = fetchMock.mock.calls.find(([input]) => urlOf(input).includes('/api/compose'));
    expect(bodyOf(call?.[1])).toEqual({ topic: '写一篇科研进展推文' });
  });

  it('接口失败时显示错误，不伪造草稿', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(jsonResponse({ detail: '未配置 DEEPSEEK_API_KEY' }, 503))),
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

describe('写文章页 — 改稿与草稿', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('快捷指令改稿：带上原素材，产出 v2', async () => {
    const fetchMock = mockByUrl();
    const user = userEvent.setup();
    render(<Compose />);
    await user.type(screen.getByLabelText('文章选题输入框'), '写一篇科研进展推文');
    await user.click(screen.getByRole('button', { name: '生成文章' }));
    await waitFor(() => expect(screen.getByText('港城莞科研新进展')).toBeTruthy());

    await user.click(screen.getByRole('button', { name: '标题再短一点' }));

    await waitFor(() => expect(screen.getByText('科研新突破')).toBeTruthy());
    expect(screen.getByRole('button', { name: 'v2' })).toBeTruthy();

    const call = fetchMock.mock.calls.find(([input]) => urlOf(input).includes('/revise'));
    const body = bodyOf(call?.[1]) as {
      instruction: string;
      article: { title: string };
      sources: unknown[];
    };
    expect(body.instruction).toBe('标题再短一点');
    expect(body.article.title).toBe('港城莞科研新进展');
    expect(body.sources).toHaveLength(1);
  });

  it('可切回历史版本', async () => {
    mockByUrl();
    const user = userEvent.setup();
    render(<Compose />);
    await user.type(screen.getByLabelText('文章选题输入框'), '写一篇科研进展推文');
    await user.click(screen.getByRole('button', { name: '生成文章' }));
    await waitFor(() => expect(screen.getByText('港城莞科研新进展')).toBeTruthy());

    await user.click(screen.getByRole('button', { name: '标题再短一点' }));
    await waitFor(() => expect(screen.getByText('科研新突破')).toBeTruthy());

    await user.click(screen.getByRole('button', { name: 'v1' }));
    expect(screen.getByText('港城莞科研新进展')).toBeTruthy();
  });

  it('草稿落本地，重新进页面还能打开', async () => {
    mockByUrl();
    const user = userEvent.setup();
    const first = render(<Compose />);
    await user.type(screen.getByLabelText('文章选题输入框'), '写一篇科研进展推文');
    await user.click(screen.getByRole('button', { name: '生成文章' }));
    await waitFor(() => expect(screen.getByText('港城莞科研新进展')).toBeTruthy());

    first.unmount();

    render(<Compose />);
    await user.click(screen.getByRole('button', { name: /草稿箱 · 1/ }));
    await user.click(screen.getByText('写一篇科研进展推文'));
    expect(screen.getByText('港城莞科研新进展')).toBeTruthy();
  });
});
