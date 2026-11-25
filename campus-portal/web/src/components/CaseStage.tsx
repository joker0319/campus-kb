import { useEffect, useState } from 'react';
import type { MouseEvent } from 'react';
import { CASES } from '../data/cases';
import s from '../styles/case.module.css';

const INTERVAL = 5600;

/** 首页 3D 卡堆轮播：展示 RAG → Agent → 可直发成稿的链路，而非校稿命中案例。 */
export function CaseStage() {
  const [i, setI] = useState(0);
  const [paused, setPaused] = useState(false);
  const [still] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const cur = CASES[i] ?? CASES[0];

  /* 悬停暂停：用户正在读的时候不该被切走 */
  useEffect(() => {
    if (paused || still) return;
    const t = window.setInterval(() => setI((v) => (v + 1) % CASES.length), INTERVAL);
    return () => window.clearInterval(t);
  }, [paused, still]);

  /* 视差倾斜：范围压得很小（±5°/±3.5°），大幅摆动会变成廉价的漂浮海报 */
  const tilt = (e: MouseEvent<HTMLDivElement>) => {
    if (still) return;
    const el = e.currentTarget;
    const r = el.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width - 0.5;
    const py = (e.clientY - r.top) / r.height - 0.5;
    el.style.setProperty('--ry', `${(-7 + px * 10).toFixed(2)}deg`);
    el.style.setProperty('--rx', `${(2 - py * 7).toFixed(2)}deg`);
  };
  const level = (e: MouseEvent<HTMLDivElement>) => {
    setPaused(false);
    e.currentTarget.style.setProperty('--ry', '');
    e.currentTarget.style.setProperty('--rx', '');
  };

  return (
    <div className={s.wrap}>
      <div
        className={s.stage}
        onMouseMove={tilt}
        onMouseLeave={level}
        onMouseEnter={() => setPaused(true)}
      >
        <div className={s.deck}>
          <div className={s.ghost2} aria-hidden="true" />
          <div className={s.ghost} aria-hidden="true" />

          <article className={s.sheet} key={cur.id} aria-label={`成稿链路 ${cur.id}：${cur.name}`}>
            <header className={s.head}>
              <span className={s.file}>成稿链路 · {cur.phase}</span>
              <span className={s.ruleId}>{cur.id}</span>
            </header>

            <div className={s.body}>
              <span className={s.gutter}>{cur.step}</span>
              <div className={s.main}>
                <h3 className={s.sheetTitle}>{cur.name}</h3>
                <p className={s.sheetLead}>{cur.lead}</p>
                <ul className={s.points}>
                  {cur.points.map((point) => (
                    <li className={s.point} key={point}>
                      {point}
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            <div className={s.fix}>
              <span className={s.fixKey}>产出</span>
              <div>
                <p className={s.fixText}>{cur.output}</p>
                <p className={s.why}>{cur.note}</p>
              </div>
            </div>

            <footer className={s.src}>
              <span className={s.srcRule} aria-hidden="true" />
              {cur.source}
            </footer>
          </article>
        </div>
      </div>

      <div className={s.ctrl}>
        <div className={s.dots}>
          {CASES.map((c, k) => (
            <button
              key={c.id}
              type="button"
              className={s.dot}
              onClick={() => setI(k)}
              aria-label={`切到第 ${k + 1} 帧：${c.phase} ${c.name}`}
              aria-current={k === i ? 'true' : undefined}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
