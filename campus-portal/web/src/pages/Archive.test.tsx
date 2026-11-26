import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Archive from './Archive';
import type { WechatArchive, WechatArticleDetail } from '../lib/api';

const ARCHIVE: WechatArchive = {
  total: 2,
  months: [
    { month: '2026-11', count: 1 },
    { month: '2026-09', count: 1 },
  ],
  articles: [
    {
      title: '十一月科研进展',
      url: 'https://mp.weixin.qq.com/s/aaa',
      published: '2026-11-19',
      month: '2026-11',
      file: '十一月科研_20261119_WX.txt',
      excerpt: '团队在新材料方向取得突破。',
      chars: 200,
      images: 5,
    },
    {
      title: '九月活动回顾',
      url: 'https://mp.weixin.qq.com/s/bbb',
      published: '2026-09-02',
      month: '2026-09',
      file: '九月活动_20260902_WX.txt',
      excerpt: '校园开放日记录。',
      chars: 120,
      images: 3,
    },
  ],
  query: '',
  month: '',
};

const DETAIL: WechatArticleDetail = {
  title: '十一月科研进展',
  published: '2026-11-19',
  url: 'https://mp.weixin.qq.com/s/aaa',
  file: '十一月科研_20261119_WX.txt',
  text: '团队在新材料方向取得突破。\n第二行正文。',
  truncated: false,
};

describe('往期推文档案页', () => {
  beforeEach(() => {
    window.location.hash = '#/archive';
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const url = typeof input === 'string' ? input : String(input);
        if (url.startsWith('/api/archive/article')) {
          return Promise.resolve(new Response(JSON.stringify(DETAIL), { status: 200 }));
        }
        if (url.startsWith('/api/archive')) {
          const parsed = new URL(url, 'http://localhost');
          const q = parsed.searchParams.get('q') ?? '';
          const month = parsed.searchParams.get('month') ?? '';
          const filtered = ARCHIVE.articles.filter(
            (a) =>
              (!month || a.month.startsWith(month)) && (!q || `${a.title}${a.excerpt}`.includes(q)),
          );
          const body: WechatArchive = { ...ARCHIVE, articles: filtered, total: filtered.length };
          return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
        }
        throw new Error(`unexpected url ${url}`);
      }),
    );
  });

  afterEach(() => {
    window.location.hash = '';
    vi.unstubAllGlobals();
  });

  it('按月份倒序分组展示，原文链接指向微信', async () => {
    render(<Archive />);
    await waitFor(() => expect(screen.getByText('十一月科研进展')).toBeTruthy());

    const headings = screen.getAllByRole('heading', { level: 2 });
    expect(headings.map((h) => h.textContent)).toEqual(['2026 年 11 月', '2026 年 9 月']);
    expect(screen.getByText('团队在新材料方向取得突破。')).toBeTruthy();

    const links = screen.getAllByRole('link', { name: '看微信原文 ↗' });
    expect(links).toHaveLength(2);
    expect((links[0] as HTMLAnchorElement).href).toBe('https://mp.weixin.qq.com/s/aaa');
    expect((links[0] as HTMLAnchorElement).target).toBe('_blank');
  });

  it('搜索按标题或正文过滤', async () => {
    const user = userEvent.setup();
    render(<Archive />);
    await waitFor(() => expect(screen.getByText('九月活动回顾')).toBeTruthy());

    await user.type(screen.getByLabelText('搜索推文'), '新材料');
    await user.click(screen.getByRole('button', { name: '搜索' }));

    await waitFor(() => expect(screen.queryByText('九月活动回顾')).toBeNull());
    expect(screen.getByText('十一月科研进展')).toBeTruthy();
    const call = vi.mocked(fetch).mock.calls.find(([url]) => String(url).includes('q='));
    expect(String(call?.[0])).toContain('q=%E6%96%B0%E6%9D%90%E6%96%99');
  });

  it('年份+月份级联筛选，只显示选中范围、不留空分组', async () => {
    const user = userEvent.setup();
    render(<Archive />);
    await waitFor(() => expect(screen.getByText('十一月科研进展')).toBeTruthy());

    const yearBtn = screen.getByRole('button', { name: '选择年份' });
    const monthBtn = screen.getByRole('button', { name: '选择月份' });
    expect(yearBtn.textContent).toContain('全部年份');
    expect(monthBtn.textContent).toContain('全部月份');

    // 展开年份下拉，面板在按钮附近且可看到选项
    await user.click(yearBtn);
    expect(screen.getByRole('listbox', { name: '选择年份' })).toBeTruthy();
    await user.click(screen.getByRole('option', { name: /2026 年/ }));
    await waitFor(() => expect(yearBtn.textContent).toContain('2026 年'));
    // 只选年份：全年都显示
    expect(screen.getByText('十一月科研进展')).toBeTruthy();
    expect(monthBtn.textContent).toContain('全部月份');

    // 月份下拉级联到该年，选中后收窄到该月
    await user.click(monthBtn);
    await user.click(screen.getByRole('option', { name: /9 月/ }));
    await waitFor(() => expect(screen.queryByText('十一月科研进展')).toBeNull());
    expect(screen.getByText('九月活动回顾')).toBeTruthy();
    expect(screen.queryByText('2026 年 11 月')).toBeNull();

    // 换年份会清空月份，避免旧月份导致空结果
    await user.click(yearBtn);
    await user.click(screen.getByRole('option', { name: '全部年份' }));
    await waitFor(() => expect(screen.getByText('十一月科研进展')).toBeTruthy());
    expect(monthBtn.textContent).toContain('全部月份');

    await user.click(screen.getByRole('button', { name: '全部' }));
    expect(yearBtn.textContent).toContain('全部年份');
    expect(monthBtn.textContent).toContain('全部月份');
  });

  it('下拉点击外部或 Esc 关闭', async () => {
    const user = userEvent.setup();
    render(<Archive />);
    await waitFor(() => expect(screen.getByText('十一月科研进展')).toBeTruthy());

    await user.click(screen.getByRole('button', { name: '选择年份' }));
    expect(screen.getByRole('listbox', { name: '选择年份' })).toBeTruthy();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('listbox', { name: '选择年份' })).toBeNull();
  });

  it('预览正文并直达原文', async () => {
    const user = userEvent.setup();
    render(<Archive />);
    await waitFor(() => expect(screen.getByText('十一月科研进展')).toBeTruthy());

    await user.click(screen.getAllByRole('button', { name: '预览正文' })[0]!);
    await screen.findByRole('dialog');
    await waitFor(() => expect(screen.getByText('第二行正文。')).toBeTruthy());
    expect((screen.getByRole('link', { name: '打开公众号原文 ↗' }) as HTMLAnchorElement).href).toBe(
      'https://mp.weixin.qq.com/s/aaa',
    );

    await user.click(screen.getByRole('button', { name: '关闭预览' }));
    expect(screen.queryByRole('dialog')).toBeNull();
  });
});
