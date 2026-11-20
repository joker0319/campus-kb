import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import App from './App';

describe('首页', () => {
  afterEach(() => {
    window.location.hash = '';
  });

  it('导航 + 主体 + 底部结构，主角是知识库的个人助手', () => {
    render(<App />);
    expect(document.querySelector('h1')?.textContent).toContain('个人助手');
    expect(screen.getByRole('navigation', { name: '主导航' })).toBeTruthy();
    expect(screen.getByRole('link', { name: '进入知识库的个人助手' })).toBeTruthy();
  });

  it('统计条与 bento 卡片已移除，3D 轮播回到 hero 右栏', () => {
    render(<App />);
    expect(screen.queryByText('可执行校验规则')).toBeNull();
    expect(screen.queryByText('表述校对')).toBeNull();
    expect(screen.queryByText('矛盾捕获，不替人拍板')).toBeNull();
    expect(screen.queryByText('规划中')).toBeNull();
    expect(screen.queryByText(/典型问题命中/)).toBeNull();

    // 轮播（真实命中案例）保留在 hero 右栏
    const stage = document.querySelector('[class*="heroStage"]');
    expect(stage).not.toBeNull();
    expect(stage?.querySelector('[class*="sheet"]')).not.toBeNull();
  });

  it('导航与 CTA 指向助手和校稿台，顶栏提供返回', async () => {
    render(<App />);
    const links = screen.getAllByRole('link', { name: /进入助手|去校稿台|个人助手|校稿台/ });
    const hrefs = links.map((l) => l.getAttribute('href'));
    expect(hrefs).toContain('#/assistant');
    expect(hrefs).toContain('#/desk');

    window.location.hash = '#/desk';
    await new Promise((r) => setTimeout(r, 0)); // hashchange 是异步事件
    expect(screen.getByLabelText('判定依据')).toBeTruthy();
    expect(screen.getByRole('link', { name: '返回首页' })).toBeTruthy();
  });
});
