import { act, render, screen, waitFor, within } from '@testing-library/react';
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
  html: '<section style="padding:0 2px;"><h1 style="margin:0;">港城莞科研新进展</h1></section>',
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
  style: { id: 'news', name: '新闻动态', auto: true },
  figures: [
    {
      id: 'f0058',
      url: '/api/figure/f0058',
      caption: 'QS世界排名第52图文卡',
      kind: 'chart',
      width: 1080,
      height: 720,
      sourceTitle: '亚洲第4，香港第2！港城大2027QS亚洲大学排名创历史新高',
      sourcePublished: '2026-11-04',
      sectionIndex: 0,
      sectionHeading: '科研',
      score: 1.02,
      weak: false,
    },
    {
      id: 'f0090',
      url: '/api/figure/f0090',
      caption: '毕业生抛帽合影',
      kind: 'crowd',
      width: 1080,
      height: 720,
      sourceTitle: '喜讯丨港城莞41位学者入选榜单',
      sourcePublished: '2026-10-10',
      sectionIndex: 0,
      sectionHeading: '科研',
      score: 0.93,
      weak: true,
    },
  ],
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

const STYLE_NAMES: Record<string, string> = {
  news: '新闻动态',
  celebration: '喜讯捷报',
  speech: '致辞讲稿',
};

/** 按路径分流：/api/compose/revise 返回改后稿，其余返回初稿；文体跟随请求。 */
function mockByUrl() {
  const fetchMock = vi.fn((input: RequestInfo | URL, _init?: RequestInit) => {
    const url = urlOf(input);
    const asked = bodyOf(_init) as { style?: string } | null;
    const base = url.includes('/revise') ? REVISED : RESULT;
    const requested = asked?.style;
    const sid = requested && requested !== 'auto' ? requested : base.style.id;
    const payload: ComposeResult = {
      ...base,
      style: {
        id: sid,
        name: STYLE_NAMES[sid] ?? base.style.name,
        auto: !requested || requested === 'auto',
      },
    };
    if (url.includes('/compose/stream')) {
      const articleJson = JSON.stringify(payload.article);
      const cut = Math.max(1, Math.floor(articleJson.length / 2));
      const frames =
        `data: ${JSON.stringify({ type: 'meta', style: payload.style })}\n\n` +
        `data: ${JSON.stringify({ type: 'delta', text: articleJson.slice(0, cut) })}\n\n` +
        `data: ${JSON.stringify({ type: 'delta', text: articleJson.slice(cut) })}\n\n` +
        `data: ${JSON.stringify({ type: 'done', result: payload })}\n\n`;
      return Promise.resolve(
        new Response(frames, { status: 200, headers: { 'Content-Type': 'text/event-stream' } }),
      );
    }
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

  it('初始右栏完全收起，只有左侧选题区', () => {
    render(<Compose />);
    const left = screen.getByRole('complementary', { name: '选题与设置' });
    expect(within(left).getByLabelText('文章选题输入框')).toBeTruthy();
    expect(screen.queryByRole('region', { name: '文章预览' })).toBeNull();
  });

  it('提交选题后展开右栏，草稿栏固定在最上方、文章单独滚动', async () => {
    const user = userEvent.setup();
    render(<Compose />);
    await user.type(screen.getByLabelText('文章选题输入框'), '写一篇科研进展推文');
    await user.click(screen.getByRole('button', { name: '生成文章' }));

    const right = screen.getByRole('region', { name: '文章预览' });
    await waitFor(() => {
      expect(within(right).getByText('港城莞科研新进展')).toBeTruthy();
    });

    // 草稿栏是右栏的直接首元素，不在滚动容器内，才能一直固定在最上方
    const bar = within(right).getByText('草稿预览').closest('div');
    expect(bar?.parentElement).toBe(right);
    expect(right.firstElementChild).toBe(bar);
    const scroll = bar?.nextElementSibling as HTMLElement;
    expect(within(scroll).getByText('港城莞科研新进展')).toBeTruthy();

    expect(
      within(screen.getByRole('complementary', { name: '选题与设置' })).getByLabelText(
        '文章选题输入框',
      ),
    ).toBeTruthy();
  });

  it('初始态用成稿链路填住左栏下方，展开右栏后自动收起', async () => {
    const user = userEvent.setup();
    render(<Compose />);
    expect(screen.getByRole('region', { name: '成稿链路' })).toBeTruthy();
    expect(screen.getByText('从一句话到可直发')).toBeTruthy();

    await user.type(screen.getByLabelText('文章选题输入框'), '写一篇科研进展推文');
    await user.click(screen.getByRole('button', { name: '生成文章' }));
    await waitFor(() => {
      expect(screen.getByRole('region', { name: '文章预览' })).toBeTruthy();
    });
    expect(screen.queryByRole('region', { name: '成稿链路' })).toBeNull();
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
    expect(bodyOf(call?.[1])).toEqual({ topic: '写一篇科研进展推文', style: 'auto' });
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

describe('写文章页 — 文体模板', () => {
  beforeEach(() => {
    window.localStorage.clear();
    mockByUrl();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('默认按自动判断请求', async () => {
    const fetchMock = mockByUrl();
    const user = userEvent.setup();
    render(<Compose />);
    await user.type(screen.getByLabelText('文章选题输入框'), '写一篇科研进展推文');
    await user.click(screen.getByRole('button', { name: '生成文章' }));

    await waitFor(() => expect(screen.getByText('港城莞科研新进展')).toBeTruthy());
    const call = fetchMock.mock.calls.find(([input]) => urlOf(input).includes('/api/compose'));
    expect(bodyOf(call?.[1])).toMatchObject({ style: 'auto' });
    // auto 判成新闻，结果区要标出「自动 · 新闻动态」
    expect(screen.getByText('自动 · 新闻动态')).toBeTruthy();
  });

  it('选喜讯捷报后按该文体请求，并沿用同一文体改稿', async () => {
    const fetchMock = mockByUrl();
    const user = userEvent.setup();
    render(<Compose />);

    await user.click(screen.getByRole('button', { name: '喜讯捷报' }));
    await user.type(screen.getByLabelText('文章选题输入框'), '写一篇学者入选榜单的推文');
    await user.click(screen.getByRole('button', { name: '生成文章' }));
    await waitFor(() => expect(screen.getByText('港城莞科研新进展')).toBeTruthy());

    const gen = fetchMock.mock.calls.find(([input]) => urlOf(input).includes('/api/compose'));
    expect(bodyOf(gen?.[1])).toMatchObject({ style: 'celebration' });

    await user.click(screen.getByRole('button', { name: '标题再短一点' }));
    await waitFor(() => expect(screen.getByText('科研新突破')).toBeTruthy());

    const rev = fetchMock.mock.calls.find(([input]) => urlOf(input).includes('/revise'));
    expect(bodyOf(rev?.[1])).toMatchObject({ style: 'celebration' });
  });
});

describe('写文章页 — 可用配图', () => {
  beforeEach(() => {
    window.localStorage.clear();
    mockByUrl();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('每节末尾用占位块给出图注、出处与取原图入口', async () => {
    const user = userEvent.setup();
    render(<Compose />);
    await user.type(screen.getByLabelText('文章选题输入框'), '写一篇科研进展推文');
    await user.click(screen.getByRole('button', { name: '生成文章' }));
    await waitFor(() => expect(screen.getByText('港城莞科研新进展')).toBeTruthy());

    // 占位块：有图注可读，但页面不加载真实照片（不发起 /api/figure 请求）
    const ph = screen.getByRole('img', { name: 'QS世界排名第52图文卡' });
    expect(within(ph).getByText('配图占位')).toBeTruthy();
    expect(within(ph).getByText('1080×720')).toBeTruthy();
    expect(screen.queryByAltText('QS世界排名第52图文卡')).toBeNull();
    expect(screen.getByText('图表')).toBeTruthy();
    // 来源标题与日期分两行显示：日期单独一行，长标题截断也不会把日期切掉
    expect(
      screen.getByText('《亚洲第4，香港第2！港城大2027QS亚洲大学排名创历史新高》'),
    ).toBeTruthy();
    expect(screen.getByText('2026-11-04')).toBeTruthy();
    expect(screen.getByText('配图 2 张可选')).toBeTruthy();

    const links = screen.getAllByRole<HTMLAnchorElement>('link', { name: '取原图' });
    expect(links.map((a) => a.getAttribute('href'))).toEqual([
      '/api/figure/f0058',
      '/api/figure/f0090',
    ]);
  });

  it('弱命中要标出「关联度一般」', async () => {
    const user = userEvent.setup();
    render(<Compose />);
    await user.type(screen.getByLabelText('文章选题输入框'), '写一篇科研进展推文');
    await user.click(screen.getByRole('button', { name: '生成文章' }));
    await waitFor(() => expect(screen.getByText('港城莞科研新进展')).toBeTruthy());

    expect(screen.getByText('关联度一般，请确认')).toBeTruthy();
  });
});

describe('写文章页 — 复制排版', () => {
  beforeEach(() => {
    window.localStorage.clear();
    mockByUrl();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('把 HTML 作为 text/html 写进剪贴板，粘到编辑器即带版式', async () => {
    const user = userEvent.setup();
    // userEvent.setup() 会装自己的 clipboard stub，所以要在它之后覆盖
    const write = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      value: { write, writeText: vi.fn() },
      configurable: true,
    });
    class FakeClipboardItem {
      readonly items: Record<string, Blob>;
      constructor(items: Record<string, Blob>) {
        this.items = items;
      }
    }
    vi.stubGlobal('ClipboardItem', FakeClipboardItem);

    render(<Compose />);
    await user.type(screen.getByLabelText('文章选题输入框'), '写一篇科研进展推文');
    await user.click(screen.getByRole('button', { name: '生成文章' }));
    await waitFor(() => expect(screen.getByText('港城莞科研新进展')).toBeTruthy());

    await user.click(screen.getByRole('button', { name: '复制排版' }));

    await waitFor(() => expect(write).toHaveBeenCalledTimes(1));
    const item = (write.mock.calls[0]?.[0] as FakeClipboardItem[])[0] as FakeClipboardItem;
    expect(item.items['text/html']?.type).toBe('text/html');
    // 同时带纯文本兜底：不支持富文本的编辑器至少能拿到 Markdown
    expect(item.items['text/plain']?.type).toBe('text/plain');
    expect(screen.getByRole('button', { name: '已复制排版' })).toBeTruthy();
  });

  it('剪贴板不可写时按钮回到未复制状态，不抛错', async () => {
    const user = userEvent.setup();
    Object.defineProperty(navigator, 'clipboard', {
      value: { write: vi.fn().mockRejectedValue(new Error('denied')), writeText: vi.fn() },
      configurable: true,
    });
    vi.stubGlobal(
      'ClipboardItem',
      class {
        constructor(readonly items: Record<string, Blob>) {}
      },
    );

    render(<Compose />);
    await user.type(screen.getByLabelText('文章选题输入框'), '写一篇科研进展推文');
    await user.click(screen.getByRole('button', { name: '生成文章' }));
    await waitFor(() => expect(screen.getByText('港城莞科研新进展')).toBeTruthy());

    await user.click(screen.getByRole('button', { name: '复制排版' }));

    await waitFor(() => expect(screen.getByRole('button', { name: '复制排版' })).toBeTruthy());
  });
});

describe('写文章页 — 流式成稿', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  /** 手动推帧的假后端：能卡在"写到一半"检查中间态。 */
  function controlledStream() {
    const encoder = new TextEncoder();
    let push: (frame: string) => void = () => {};
    let close: () => void = () => {};
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        push = (frame) => controller.enqueue(encoder.encode(frame));
        close = () => controller.close();
      },
    });
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(new Response(body, { status: 200 }))),
    );
    return { push, close };
  }

  it('边写边显示：已写完的段落先出现，收完才给成品操作', async () => {
    const { push, close } = controlledStream();
    const user = userEvent.setup();
    render(<Compose />);
    await user.type(screen.getByLabelText('文章选题输入框'), '写一篇科研进展推文');
    await user.click(screen.getByRole('button', { name: '生成文章' }));

    await waitFor(() => expect(screen.getByText('正在成稿')).toBeTruthy());
    expect(screen.getByText('正在检索素材、构思结构…')).toBeTruthy();

    act(() => {
      push(`data: ${JSON.stringify({ type: 'meta', style: RESULT.style })}\n\n`);
      push(
        `data: ${JSON.stringify({
          type: 'delta',
          text: '{"title":"半成品标题","lead":"导语一句话","sections":[{"heading":"科研","paragraphs":[{"text":"已经写完的一段。"}]}',
        })}\n\n`,
      );
    });

    await waitFor(() => expect(screen.getByText('半成品标题')).toBeTruthy());
    expect(screen.getByText('已经写完的一段。')).toBeTruthy();
    expect(screen.getByText('科研')).toBeTruthy();
    // 还没收完，不应该出现成品态的操作
    expect(screen.queryByRole('button', { name: '复制排版' })).toBeNull();

    act(() => {
      push(`data: ${JSON.stringify({ type: 'done', result: RESULT })}\n\n`);
      close();
    });

    await waitFor(() => expect(screen.getByRole('button', { name: '复制排版' })).toBeTruthy());
    expect(screen.getByText('港城莞科研新进展')).toBeTruthy();
  });

  it('流里的 error 事件转成页面报错', async () => {
    const { push, close } = controlledStream();
    const user = userEvent.setup();
    render(<Compose />);
    await user.type(screen.getByLabelText('文章选题输入框'), '写一篇科研进展推文');
    await user.click(screen.getByRole('button', { name: '生成文章' }));

    await waitFor(() => expect(screen.getByText('正在成稿')).toBeTruthy());

    act(() => {
      push(`data: ${JSON.stringify({ type: 'error', message: '模型返回内容不完整，请重试' })}\n\n`);
      close();
    });

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toContain('模型返回内容不完整');
  });
});

describe('写文章页 — 一键流水线', () => {
  const PIPELINE_RESULT: ComposeResult = {
    ...RESULT,
    pipeline: {
      autoRevise: true,
      revisions: [
        {
          instruction: '把校名写全称',
          before: { error: 1, warn: 0 },
          after: { error: 0, warn: 0 },
        },
      ],
      finalCounts: { total: 0, error: 0, warn: 0, info: 0 },
    },
  };

  function mockPipeline() {
    return vi.fn((input: RequestInfo | URL, _init?: RequestInit) => {
      const url = urlOf(input);
      if (url.includes('/api/pipeline/stream')) {
        const articleJson = JSON.stringify(RESULT.article);
        const cut = Math.max(1, Math.floor(articleJson.length / 2));
        const frames =
          `data: ${JSON.stringify({
            type: 'meta',
            style: RESULT.style,
            steps: [
              { id: 'retrieve', label: '检索语料' },
              { id: 'compose', label: 'Agent 成稿' },
              { id: 'review', label: '发前检查' },
              { id: 'export', label: '排版导出' },
            ],
            sourceCount: 12,
          })}\n\n` +
          `data: ${JSON.stringify({ type: 'step', id: 'retrieve', label: '检索语料', detail: '命中 12 条素材' })}\n\n` +
          `data: ${JSON.stringify({ type: 'delta', text: articleJson.slice(0, cut) })}\n\n` +
          `data: ${JSON.stringify({ type: 'step', id: 'compose', label: 'Agent 成稿', detail: '完成 1 个段落' })}\n\n` +
          `data: ${JSON.stringify({ type: 'delta', text: articleJson.slice(cut) })}\n\n` +
          `data: ${JSON.stringify({ type: 'step', id: 'review', label: '发前检查', detail: '1 错 / 0 警' })}\n\n` +
          `data: ${JSON.stringify({ type: 'step', id: 'revise', label: '自动修订', detail: '修正 1 项' })}\n\n` +
          `data: ${JSON.stringify({ type: 'step', id: 'export', label: '排版导出', detail: 'HTML 已就绪' })}\n\n` +
          `data: ${JSON.stringify({ type: 'done', result: PIPELINE_RESULT })}\n\n`;
        return Promise.resolve(
          new Response(frames, { status: 200, headers: { 'Content-Type': 'text/event-stream' } }),
        );
      }
      return Promise.resolve(jsonResponse(PIPELINE_RESULT));
    });
  }

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('一键成稿按钮走 pipeline 接口并带 autoRevise', async () => {
    const fetchMock = mockPipeline();
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();
    render(<Compose />);
    await user.type(screen.getByLabelText('文章选题输入框'), '写一篇科研进展推文');
    await user.click(screen.getByRole('button', { name: '一键成稿' }));

    await waitFor(() => expect(screen.getByText('港城莞科研新进展')).toBeTruthy());
    const call = fetchMock.mock.calls.find(([input]) => urlOf(input).includes('/pipeline/stream'));
    expect(bodyOf(call?.[1])).toEqual({
      topic: '写一篇科研进展推文',
      style: 'auto',
      autoRevise: true,
    });
  });

  it('成稿后显示自动修订标记', async () => {
    vi.stubGlobal('fetch', mockPipeline());
    const user = userEvent.setup();
    render(<Compose />);
    await user.type(screen.getByLabelText('文章选题输入框'), '写一篇科研进展推文');
    await user.click(screen.getByRole('button', { name: '一键成稿' }));

    await waitFor(() => expect(screen.getByText(/已自动修订 1 轮/)).toBeTruthy());
  });

  it('初始态说明文案体现一键串联', () => {
    render(<Compose />);
    expect(screen.getByText(/输入一句话，助手自动检索、成稿/)).toBeTruthy();
    expect(screen.getByText(/有问题自动修订一轮/)).toBeTruthy();
  });
});
