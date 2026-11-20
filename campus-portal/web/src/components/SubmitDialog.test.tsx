import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { SubmitDialog } from './SubmitDialog';
import { DRAFT_TEXT } from '../data/content';

describe('SubmitDialog', () => {
  it('渲染标题、正文输入区与操作按钮', () => {
    render(<SubmitDialog onClose={vi.fn()} onSubmit={vi.fn()} />);
    expect(screen.getByRole('dialog', { name: '粘贴稿件' })).toBeTruthy();
    expect(screen.getByLabelText('稿件正文')).toBeTruthy();
    expect(screen.getByRole('button', { name: '校验这篇' })).toBeTruthy();
    expect(screen.getByRole('button', { name: '关闭' })).toBeTruthy();
  });

  it('空文本时提交禁用；输入后统计字数行数并提交 trim 后的正文', () => {
    const onSubmit = vi.fn();
    render(<SubmitDialog onClose={vi.fn()} onSubmit={onSubmit} />);
    const submitBtn = screen.getByRole<HTMLButtonElement>('button', { name: '校验这篇' });
    expect(submitBtn.disabled).toBe(true);

    const area = screen.getByLabelText<HTMLTextAreaElement>('稿件正文');
    fireEvent.change(area, { target: { value: '  标题\n正文  ' } });
    expect(screen.getByText(/5 字 · 2 行/)).toBeTruthy();
    expect(submitBtn.disabled).toBe(false);

    fireEvent.click(submitBtn);
    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit).toHaveBeenCalledWith('标题\n正文');
  });

  it('「填入示例」把内置样例载入输入框', () => {
    render(<SubmitDialog onClose={vi.fn()} onSubmit={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: '填入示例' }));
    const area = screen.getByLabelText<HTMLTextAreaElement>('稿件正文');
    expect(area.value).toBe(DRAFT_TEXT);
  });

  it('Escape 与点击遮罩关闭；点击面板内部不关闭', () => {
    const onClose = vi.fn();
    render(<SubmitDialog onClose={onClose} onSubmit={vi.fn()} />);

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);

    const overlay = screen.getByRole('presentation');
    const panel = screen.getByRole('dialog', { name: '粘贴稿件' });
    fireEvent.mouseDown(panel);
    expect(onClose).toHaveBeenCalledTimes(1);
    fireEvent.mouseDown(overlay);
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});
