/**
 * 数字滚动。rAF 时间戳可能早于 performance.now()，差值为负会让缓动输出
 * 负数（页面曾出现过 -368），因此进度 p 必须钳制在 [0,1]。
 */
export function easeOutCubic(p: number): number {
  const c = Math.min(Math.max(p, 0), 1);
  return 1 - Math.pow(1 - c, 3);
}

/** 滚动 el 的文本到 target，返回取消函数 */
export function countUp(el: HTMLElement, target: number, duration = 900): () => void {
  let raf = 0;
  let start: number | null = null;
  const tick = (now: number) => {
    if (start === null) start = now;
    el.textContent = String(Math.round(target * easeOutCubic((now - start) / duration)));
    if ((now - start) / duration < 1) raf = requestAnimationFrame(tick);
  };
  raf = requestAnimationFrame(tick);
  return () => cancelAnimationFrame(raf);
}
