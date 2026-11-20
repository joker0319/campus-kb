import { render, screen, waitFor, cleanup } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { CorpusSearch } from './CorpusSearch';

afterEach(cleanup);

const OK_BODY = {
  query: '于吉红',
  total: 1,
  scanned: 26,
  results: [
    {
      file: '奠基仪式主持词',
      line: 26,
      excerpt: '请于吉红院士、梁维东书记…',
      hits: 4,
    },
  ],
};

describe('CorpusSearch', () => {
  it('提交关键词后渲染检索结果', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(OK_BODY),
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<CorpusSearch onClose={() => {}} />);
    await userEvent.type(screen.getByRole('searchbox'), '于吉红');
    await userEvent.click(screen.getByRole('button', { name: '检索' }));

    await waitFor(() => {
      expect(screen.getByText(/命中 1 行/)).toBeTruthy();
    });
    expect(screen.getByText('奠基仪式主持词')).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith('/api/search?q=%E4%BA%8E%E5%90%89%E7%BA%A2');
  });

  it('接口失败时显示错误信息', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500 }));
    render(<CorpusSearch onClose={() => {}} />);
    await userEvent.type(screen.getByRole('searchbox'), 'x');
    await userEvent.click(screen.getByRole('button', { name: '检索' }));
    await waitFor(() => {
      expect(screen.getByText(/检索失败：接口返回 500/)).toBeTruthy();
    });
  });

  it('空关键词不发请求', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    render(<CorpusSearch onClose={() => {}} />);
    await userEvent.click(screen.getByRole('button', { name: '检索' }));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('Escape 键关闭面板', async () => {
    const onClose = vi.fn();
    render(<CorpusSearch onClose={onClose} />);
    await userEvent.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalled();
  });
});
