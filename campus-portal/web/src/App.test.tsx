import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import reviewFixture from './test/fixtures/review.json';

const list = () => screen.getAllByRole('listitem');
const evidence = () => screen.getByLabelText('判定依据');
const chip = (name: RegExp) => screen.getByRole('tab', { name });

/** 等待真实接口返回并渲染完 17 条命中 */
async function ready() {
  await waitFor(() => expect(list()).toHaveLength(17));
}

function mockReview(body: unknown = reviewFixture) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(body),
    }),
  );
}

/** 多次请求依次返回不同响应（用于验证粘贴新稿件后的动态替换） */
function mockReviewSequence(...bodies: unknown[]) {
  let i = 0;
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(() => {
      const body = bodies[Math.min(i++, bodies.length - 1)];
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve(body),
      });
    }),
  );
}

/** 只保留一条命中的响应：新稿件的 NAME-001@3 */
const customFixture = {
  ...reviewFixture,
  findings: [reviewFixture.findings[3]!],
  counts: { total: 1, error: 1, warn: 0, info: 0 },
};

describe('校稿台（接真实 /api/review）', () => {
  beforeEach(() => {
    window.location.hash = '#/desk';
    mockReview();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    window.location.hash = '';
  });

  it('渲染 17 条命中，与引擎输出一致', async () => {
    render(<App />);
    await ready();
    expect(list()).toHaveLength(17);
  });

  it('默认选中 NAME-001，依据栏给出规则名、原文与出处', async () => {
    render(<App />);
    await ready();
    const pane = evidence();
    expect(within(pane).getByText('校名首次出现用全称')).toBeTruthy();
    expect(within(pane).getByText(/全称：香港城市大学（东莞）/)).toBeTruthy();
    expect(within(pane).getByText(/一、学校定位与基本信息/)).toBeTruthy();
  });

  it('点选问题后依据栏切换到对应规则', async () => {
    render(<App />);
    await ready();
    const item = screen.getByText(/中、港、台.*并列提法/).closest('[role="listitem"]');
    expect(item).not.toBeNull();
    fireEvent.click(within(item as HTMLElement).getByRole('button', { pressed: false }));

    const pane = evidence();
    expect(within(pane).getByText('SOEV-002')).toBeTruthy();
    expect(within(pane).getByText(/海峡两岸暨香港/)).toBeTruthy();
  });

  it('按级别筛选：错误 11 条 / 警告 6 条', async () => {
    render(<App />);
    await ready();
    fireEvent.click(chip(/错误/));
    expect(list()).toHaveLength(11);

    fireEvent.click(chip(/警告/));
    expect(list()).toHaveLength(6);
  });

  it('忽略一条后从清单移除，计数同步', async () => {
    render(<App />);
    await ready();
    const first = list()[0] as HTMLElement;
    fireEvent.click(within(first).getByTitle('忽略这条'));

    expect(list()).toHaveLength(16);
    expect(within(chip(/全部/)).getByText('16')).toBeTruthy();
  });

  it('关掉「显示标记」后正文进入纯净阅读态', async () => {
    const { container } = render(<App />);
    await ready();
    const prose = container.querySelector('[class*="prose"]') as HTMLElement;
    expect(prose.className).not.toContain('plain');

    fireEvent.click(screen.getByLabelText('显示标记'));
    expect(prose.className).toContain('plain');
  });

  it('键盘 j 逐条向下、k 回退', async () => {
    render(<App />);
    await ready();
    // 初始 NAME-001@3，下一条是同行的 PUNCT-001@3
    fireEvent.keyDown(window, { key: 'j' });
    expect(within(evidence()).getByText('中文语境用全角标点')).toBeTruthy();

    fireEvent.keyDown(window, { key: 'k' });
    expect(within(evidence()).getByText('校名首次出现用全称')).toBeTruthy();
  });

  it('接口失败时显示错误态，不回落假数据', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 503 }));
    render(<App />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    expect(screen.getByText(/校验接口不可用：校验接口返回 503/)).toBeTruthy();
    expect(screen.queryAllByRole('listitem')).toHaveLength(0);
  });

  it('「重新校验」会重新请求接口', async () => {
    render(<App />);
    await ready();
    const fetchMock = vi.mocked(fetch);
    expect(fetchMock).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: '重新校验' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });

  it('粘贴自定义稿件：提交新正文后按新命中替换清单并标红', async () => {
    const customText = '【媒体传讯处】测试\n通知动态\n港城大（东莞）校长出席活动。';
    mockReviewSequence(reviewFixture, customFixture);
    render(<App />);
    await ready();

    fireEvent.click(screen.getByRole('button', { name: '粘贴稿件' }));
    const dialog = await screen.findByRole('dialog', { name: '粘贴稿件' });
    fireEvent.change(within(dialog).getByLabelText('稿件正文'), {
      target: { value: customText },
    });
    fireEvent.click(within(dialog).getByRole('button', { name: '校验这篇' }));

    await waitFor(() => expect(list()).toHaveLength(1));
    const fetchMock = vi.mocked(fetch);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(JSON.parse((fetchMock.mock.calls[1]![1] as RequestInit).body as string)).toEqual({
      content: customText,
      mode: 'submission',
    });
    expect(screen.getByText('自定义稿件')).toBeTruthy();

    // 新正文按 hit 标红：第 3 行的「港城大（东莞）」可点回依据
    const marked = screen.getByText('港城大（东莞）');
    expect(marked.getAttribute('role')).toBe('button');
    expect(marked.getAttribute('title')).toContain('点击查看依据');
  });
});
