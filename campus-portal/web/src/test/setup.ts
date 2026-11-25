import { cleanup } from '@testing-library/react';
import { afterEach, vi } from 'vitest';

// 未开启 globals 时 testing-library 不会自动清理，DOM 会在用例间累积
afterEach(cleanup);

// jsdom 没有实现这两个 API，App 的响应式与滚动定位依赖它们
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: query.includes('min-width'),
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }),
});

Element.prototype.scrollIntoView = vi.fn();
// App 路由切换会调 window.scrollTo(0, 0)，jsdom 未实现会刷一屏告警
Object.defineProperty(window, 'scrollTo', { writable: true, value: vi.fn() });
