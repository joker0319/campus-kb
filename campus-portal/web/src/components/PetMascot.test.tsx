import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { PetMascot } from './PetMascot';

const bubble = () => document.querySelector('[class*="bubble"]')?.textContent;

describe('墨点小助手', () => {
  it('默认说第一条，且是可点击按钮', () => {
    render(<PetMascot />);
    expect(bubble()).toBe('今天扫了 17 处问题，3 处是校名简称。');
    expect(screen.getByRole('button', { name: '点一下，换一条校验提示' })).toBeTruthy();
  });

  it('点一下换下一条台词', () => {
    render(<PetMascot />);
    fireEvent.click(screen.getByRole('button', { name: '点一下，换一条校验提示' }));
    expect(bubble()).toBe('「中、港、台」这种写法，我不会放过。');
  });

  it('连点循环回到第一条', () => {
    render(<PetMascot />);
    const btn = screen.getByRole('button', { name: '点一下，换一条校验提示' });
    for (let i = 0; i < 5; i++) fireEvent.click(btn);
    expect(bubble()).toBe('今天扫了 17 处问题，3 处是校名简称。');
  });

  it('台词不重复（点满一轮五条各不相同）', () => {
    render(<PetMascot />);
    const btn = screen.getByRole('button', { name: '点一下，换一条校验提示' });
    const seen = new Set([bubble()]);
    for (let i = 0; i < 4; i++) {
      fireEvent.click(btn);
      seen.add(bubble());
    }
    expect(seen.size).toBe(5);
  });
});
