import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import App from '../App';

describe('助手页', () => {
  afterEach(() => {
    window.location.hash = '';
  });

  it('#/assistant 渲染助手界面壳，明确标注能力待接入', async () => {
    window.location.hash = '#/assistant';
    render(<App />);
    await new Promise((r) => setTimeout(r, 0));

    expect(screen.getByRole('heading', { name: '有什么可以帮你？' })).toBeTruthy();
    expect(screen.getByRole('link', { name: '← 返回首页' })).toBeTruthy();
    expect(screen.getAllByText('接入中')).toHaveLength(3);
    expect(screen.getByLabelText('助手输入框')).toBeTruthy();
  });

  it('输入框与发送按钮禁用，不伪装生成回答', async () => {
    window.location.hash = '#/assistant';
    render(<App />);
    await new Promise((r) => setTimeout(r, 0));

    expect(screen.getByLabelText<HTMLInputElement>('助手输入框').disabled).toBe(true);
    expect(screen.getByRole<HTMLButtonElement>('button', { name: '发送' }).disabled).toBe(true);
    expect(screen.getByText(/暂不生成任何回答/)).toBeTruthy();
  });
});
