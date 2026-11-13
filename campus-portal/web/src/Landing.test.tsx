import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import App from './App';

describe('首页', () => {
  afterEach(() => {
    window.location.hash = '';
  });

  it('默认路由渲染首页：hero、统计与 bento 卡片', () => {
    render(<App />);
    expect(document.querySelector('h1')?.textContent).toContain('稿件前置检查');

    expect(screen.getByText('可执行校验规则')).toBeTruthy();
    expect(screen.getByText('表述校对')).toBeTruthy();
    expect(screen.getByText('矛盾捕获，不替人拍板')).toBeTruthy();
    // 未实现的模块明确标注规划中，不做空头承诺
    expect(screen.getByText('规划中')).toBeTruthy();
  });

  it('全部数字可溯源：9 / 19 / 17 / 0', () => {
    // 以 reduced-motion 路径渲染：跳过动效，统计直接显示终值
    const orig = window.matchMedia.bind(window);
    window.matchMedia = (q) => ({ ...orig(q), matches: true });
    try {
      const { container } = render(<App />);
      const nums = [...container.querySelectorAll('[class*="statNum"] span')].map(
        (el) => el.textContent,
      );
      expect(nums).toEqual(['9', '19', '17', '0']);
    } finally {
      window.matchMedia = orig;
    }
  });

  it('入口指向校稿台，顶栏提供返回', async () => {
    render(<App />);
    const cta = screen.getAllByRole('link', { name: /进入校稿台/ })[0] as HTMLAnchorElement;
    expect(cta.getAttribute('href')).toBe('#/desk');

    window.location.hash = '#/desk';
    await new Promise((r) => setTimeout(r, 0)); // hashchange 是异步事件
    expect(screen.getByLabelText('判定依据')).toBeTruthy();
    expect(screen.getByRole('link', { name: '返回首页' })).toBeTruthy();
  });
});
