import { act, fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CaseStage } from './CaseStage';

describe('首页成稿链路轮播', () => {
  it('首帧是知识库：阶段编号、语料规模与三条要点', () => {
    const { container } = render(<CaseStage />);
    expect(screen.getByText('STAGE-01')).toBeTruthy();
    expect(screen.getByText('语料进库，先有据可查')).toBeTruthy();
    expect(container.querySelectorAll('li').length).toBe(3);
  });

  it('切到第二帧后标题、产出与来源同时更新', () => {
    render(<CaseStage />);
    fireEvent.click(screen.getByLabelText(/切到第 2 帧/));
    expect(screen.getByText('STAGE-02')).toBeTruthy();
    expect(screen.getByText('一句话选题，边写边出稿')).toBeTruthy();
    expect(screen.getByText(/SSE 流式成稿/)).toBeTruthy();
  });

  it('末帧落在可直发成稿，校稿只作为其中一环', () => {
    render(<CaseStage />);
    fireEvent.click(screen.getByLabelText(/切到第 3 帧/));
    expect(screen.getByText('复制排版 → 粘贴 → 一篇能直接发出的公众号文章')).toBeTruthy();
    expect(screen.getByText(/校稿只是其中一个环节/)).toBeTruthy();
  });

  it('指针悬停时暂停轮播，移出后继续', () => {
    vi.useFakeTimers();
    try {
      const { container } = render(<CaseStage />);
      const stage = container.querySelector('[class*="stage"]') as HTMLElement;

      // 悬停：5.6s 后仍停在第一帧
      fireEvent.mouseOver(stage);
      act(() => void vi.advanceTimersByTime(6000));
      expect(screen.getByText('STAGE-01')).toBeTruthy();

      // 移出：定时器恢复，切到下一帧
      fireEvent.mouseOut(stage);
      act(() => void vi.advanceTimersByTime(6000));
      expect(screen.getByText('STAGE-02')).toBeTruthy();
    } finally {
      vi.useRealTimers();
    }
  });
});
