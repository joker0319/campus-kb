import { useEffect, useRef, useState } from 'react';
import s from '../styles/pet.module.css';

/* 台词全部取自真实校验结果，不做无信息的可爱话 */
const LINES = [
  '今天扫了 17 处问题，3 处是校名简称。',
  '「中、港、台」这种写法，我不会放过。',
  '手册自己也错了一次：52rd 应该是 52nd。',
  '没有出处的判定，我直接说不知道。',
  '规则库 v1 · 19 条 · 依据手册 2026.05。',
];

export function PetMascot() {
  const [line, setLine] = useState(0);
  const [pop, setPop] = useState(0);
  const pet = useRef<HTMLButtonElement>(null);
  const [still] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches);

  /* 瞳孔跟随指针：只改两个 CSS 变量，不用 state，避免每次移动都重渲染 */
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
        /* 偏移量随尺寸等比放大，否则小助手放大后瞳孔几乎不动 */
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

  const poke = () => {
    setPop((v) => v + 1);
    setLine((v) => (v + 1) % LINES.length);
  };

  return (
    <div className={s.row}>
      <button
        ref={pet}
        type="button"
        className={s.pet}
        onClick={poke}
        data-pop={pop % 2 === 1 ? '1' : pop % 2 === 0 && pop > 0 ? '2' : '0'}
        aria-label="点一下，换一条校验提示"
      >
        {/* viewBox 裁到图形本身：留白会让「放大」只放大透明区 */}
        <svg className={s.svg} viewBox="10 6 44 54" aria-hidden="true" focusable="false">
          <g className={s.breathe}>
            <g className={s.pop}>
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
          </g>
        </svg>
      </button>

      <p className={s.bubble} key={line} aria-live="polite">
        {LINES[line]}
      </p>
    </div>
  );
}
