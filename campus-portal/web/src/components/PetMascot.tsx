import { useEffect, useRef, useState } from 'react';
import s from '../styles/pet.module.css';

/**
 * 墨点：知识库个人助手的入口。
 * 点击整块（精灵 + 气泡）进入 #/assistant；保留呼吸 / 眨眼 / 瞳孔跟随的静止感动画。
 */
export function PetMascot() {
  const pet = useRef<HTMLSpanElement>(null);
  const [still] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches);

  /* 瞳孔跟随指针：只改 CSS 变量，不用 state，避免每次移动都重渲染 */
  useEffect(() => {
    const el = pet.current;
    if (!el || still) return;
    let raf = 0;
    const onMove = (e: PointerEvent) => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        const r = el.getBoundingClientRect();
        const dx = e.clientX - (r.left + r.width / 2);
        const dy = e.clientY - (r.top + r.height / 2);
        const d = Math.hypot(dx, dy) || 1;
        /* 偏移量随尺寸等比放大，否则放大后瞳孔几乎不动 */
        const k = Math.min(d / (r.width * 4.3), 1) * (r.width / 26.7);
        el.style.setProperty('--gx', `${((dx / d) * k).toFixed(2)}px`);
        el.style.setProperty('--gy', `${((dy / d) * k).toFixed(2)}px`);
      });
    };
    window.addEventListener('pointermove', onMove, { passive: true });
    return () => {
      window.removeEventListener('pointermove', onMove);
      cancelAnimationFrame(raf);
    };
  }, [still]);

  return (
    <a className={s.entry} href="#/assistant" aria-label="进入知识库的个人助手">
      <span className={s.pet} ref={pet}>
        {/* viewBox 裁到图形本身：留白会让「放大」只放大透明区 */}
        <svg className={s.svg} viewBox="10 6 44 54" aria-hidden="true" focusable="false">
          <g className={s.breathe}>
            <line className={s.stem} x1="32" y1="23" x2="32" y2="13" />
            <circle className={s.tip} cx="32" cy="10.6" r="2.9" />
            <path
              className={s.body}
              d="M32 22c8.2 0 15.2 7 16.4 17C49.6 49 41.4 57 32 57S14.4 49 15.6 39C16.8 29 23.8 22 32 22Z"
            />
            <g className={s.eyes}>
              <ellipse className={s.eye} cx="25.6" cy="37" rx="5.1" ry="5.7" />
              <ellipse className={s.eye} cx="38.4" cy="37" rx="5.1" ry="5.7" />
              <g className={s.pupils}>
                <circle className={s.pupil} cx="25.6" cy="37.6" r="2.35" />
                <circle className={s.pupil} cx="38.4" cy="37.6" r="2.35" />
              </g>
            </g>
            <path className={s.mouth} d="M28.6 47.2q3.4 2.6 6.8 0" />
          </g>
        </svg>
      </span>

      <span className={s.copy}>
        <b className={s.title}>知识库的个人助手</b>
        <span className={s.bubble}>问我规范、查档案、校稿件，点这里开始 →</span>
      </span>
    </a>
  );
}
