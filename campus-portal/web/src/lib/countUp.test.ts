import { describe, expect, it, vi } from 'vitest';
import { countUp, easeOutCubic } from './countUp';

describe('easeOutCubic', () => {
  it('边界：0→0，1→1，负数与超出范围一律钳制', () => {
    expect(easeOutCubic(0)).toBe(0);
    expect(easeOutCubic(1)).toBe(1);
    expect(easeOutCubic(-1)).toBe(0); // rAF 时间戳早于 start 时 p 为负
    expect(easeOutCubic(2)).toBe(1);
  });

  it('单调递增且不超过 1', () => {
    let prev = -1;
    for (let p = 0; p <= 1.0001; p += 0.05) {
      const v = easeOutCubic(p);
      expect(v).toBeGreaterThanOrEqual(prev);
      expect(v).toBeLessThanOrEqual(1);
      prev = v;
    }
  });
});

describe('countUp', () => {
  it('滚动到目标值并停止，不产生负数', () => {
    const el = document.createElement('span');
    let t = 0;
    // 用同步递增的 rAF 桩驱动动画到结束
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
      t += 100;
      cb(t);
      return t;
    });

    const cancel = countUp(el, 19, 900);
    cancel();

    expect(el.textContent).toBe('19');
    vi.unstubAllGlobals();
  });
});
