import { act, fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { CaseStage } from './CaseStage';

describe('稿件案例轮播', () => {
  it('首屏显示第一个案例，命中词被包成标记', () => {
    const { container } = render(<CaseStage />);
    expect(screen.getByText('NAME-001')).toBeTruthy();
    const marks = [...container.querySelectorAll('mark')].map((m) => m.textContent);
    expect(marks).toEqual(['港城大（东莞）']);
  });

  it('切到第二个案例后，正文与改法同时更新', () => {
    render(<CaseStage />);
    fireEvent.click(screen.getByLabelText(/切到案例 2/));
    expect(screen.getByText('SOEV-002')).toBeTruthy();
    expect(screen.getByText('以及海峡两岸暨香港的青年学者共同研讨。')).toBeTruthy();
  });

  it('一处案例可以有多个命中标记', () => {
    const { container } = render(<CaseStage />);
    fireEvent.click(screen.getByLabelText(/切到案例 3/));
    const marks = [...container.querySelectorAll('mark')].map((m) => m.textContent);
    expect(marks).toEqual(['第63位', '52rd']);
  });

  it('指针悬停时暂停轮播，移出后继续', () => {
    vi.useFakeTimers();
    try {
      const { container } = render(<CaseStage />);
      const stage = container.querySelector('[class*="stage"]') as HTMLElement;

      // 悬停：5.6s 后仍停在第一个案例
      fireEvent.mouseOver(stage);
      act(() => void vi.advanceTimersByTime(6000));
      expect(screen.getByText('NAME-001')).toBeTruthy();

      // 移出：定时器恢复，切到下一个
      fireEvent.mouseOut(stage);
      act(() => void vi.advanceTimersByTime(6000));
      expect(screen.getByText('SOEV-002')).toBeTruthy();
    } finally {
      vi.useRealTimers();
    }
  });
});
