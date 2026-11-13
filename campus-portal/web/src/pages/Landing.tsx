import { useEffect, useRef, useState } from 'react';
import type { CSSProperties, MouseEvent } from 'react';
import { countUp } from '../lib/countUp';
import { CaseStage } from '../components/CaseStage';
import { PetMascot } from '../components/PetMascot';
import s from '../styles/landing.module.css';

/* 所有数字与案例都来自 campus-kb 实测，禁止编造 */
const STATS = [
  { num: 9, unit: '份', label: '规范资料入库' },
  { num: 19, unit: '条', label: '可执行校验规则' },
  { num: 17, unit: '项', label: '典型问题命中' },
  { num: 0, unit: '', label: '合规稿对照组误报' },
] as const;

const CARDS = [
  {
    tag: 'NAME-001 · TITLE-001',
    title: '表述校对',
    body: '校名全称、头衔职务、港澳台表述、标点全半角。19 条规则逐行检查，命中处标红并给出改法。',
    planned: false,
  },
  {
    tag: 'SOEV-002',
    title: '判定依据',
    body: '每一处标记都能点回规范原文的章与条。没有出处的判定一律不输出。',
    planned: false,
  },
  {
    tag: 'RANK-001 实例',
    title: '矛盾捕获，不替人拍板',
    body: '手册中文版写「2027 年 QS 第 63 位」，英文版写 52rd。规则只报告冲突，权威值由传讯处确认；规则不跟随手册自身的错误。',
    planned: false,
  },
  {
    tag: '规划中 · P1',
    title: '模板填槽出初稿',
    body: '把《报送模板》变成填空题：主题、时间、地点、要点进去，符合全部格式要求的初稿出来。',
    planned: true,
  },
] as const;

const STEPS = [
  { n: '01', t: '打开稿件', d: '粘贴正文或导入文件' },
  { n: '02', t: '引擎校验', d: '19 条规则 · 0.4 秒' },
  { n: '03', t: '逐条核对依据', d: '标记回链规范条款' },
  { n: '04', t: '生成批注报告', d: '随稿交付给作者' },
] as const;

const D = (v: string) => ({ '--d': v }) as CSSProperties;

export default function Landing() {
  /* 入场编排只演一次：结束后摘掉运行态标记，DOM 回到纯静态样式 */
  const [run] = useState(() => !window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const [on, setOn] = useState(run);
  const nums = useRef<(HTMLSpanElement | null)[]>([]);

  useEffect(() => {
    if (!run) return;
    const stops = STATS.map((st, i) => {
      const el = nums.current[i];
      if (!el) return () => undefined;
      const t = window.setTimeout(() => countUp(el, st.num, 900), 760 + i * 80);
      return () => {
        window.clearTimeout(t);
        el.textContent = String(st.num);
      };
    });
    const done = window.setTimeout(() => setOn(false), 2200);
    return () => {
      window.clearTimeout(done);
      stops.forEach((fn) => fn());
    };
  }, [run]);

  /* spotlight：光斑中心跟随光标 */
  const spotlight = (e: MouseEvent<HTMLElement>) => {
    const el = e.currentTarget;
    const r = el.getBoundingClientRect();
    el.style.setProperty('--mx', `${e.clientX - r.left}px`);
    el.style.setProperty('--my', `${e.clientY - r.top}px`);
  };

  /* 磁吸：主按钮随光标轻微偏移 */
  const magnet = (e: MouseEvent<HTMLAnchorElement>) => {
    const el = e.currentTarget;
    const r = el.getBoundingClientRect();
    el.style.setProperty('--tx', `${((e.clientX - r.left - r.width / 2) / r.width) * 8}px`);
    el.style.setProperty('--ty', `${((e.clientY - r.top - r.height / 2) / r.height) * 6}px`);
  };
  const unmagnet = (e: MouseEvent<HTMLAnchorElement>) => {
    e.currentTarget.style.setProperty('--tx', '0px');
    e.currentTarget.style.setProperty('--ty', '0px');
  };

  return (
    <div className={s.page} data-run={on ? 'true' : 'false'}>
      <div className={s.bg} aria-hidden="true">
        <div className={s.bgAurora} />
        <div className={s.bgGrid} />
        <div className={s.bgNoise} />
      </div>

      <header className={s.top}>
        <div className={`${s.brand} ${s.in}`} style={D('0s')}>
          <span className={s.brandDot} />
          校园知识库 · 媒体传讯处
        </div>
        <a className={`${s.topCta} ${s.in}`} style={D('.1s')} href="#/desk">
          进入校稿台
        </a>
      </header>

      <main className={s.main}>
        <section className={s.hero}>
          <div className={s.heroCopy}>
            <h1 className={`${s.eyebrow} ${s.in}`} style={D('.05s')}>
              稿件前置检查 · 内部工具
            </h1>
            <div className={`${s.petSlot} ${s.in}`} style={D('.58s')}>
              <PetMascot />
            </div>
            <div className={`${s.actions} ${s.in}`} style={D('.7s')}>
              <a
                className={s.cta}
                href="#/desk"
                onMouseMove={magnet}
                onMouseLeave={unmagnet}
                style={{ '--tx': '0px', '--ty': '0px' } as CSSProperties}
              >
                进入校稿台
                <span className={s.ctaArrow}>→</span>
              </a>
              <a className={s.ctaGhost} href="#rules">
                看规则清单
              </a>
            </div>
          </div>

          <div className={`${s.heroStage} ${s.in}`} style={D('.3s')}>
            <CaseStage />
          </div>
        </section>

        <section className={`${s.stats} ${s.in}`} style={D('.9s')} aria-label="引擎实测数据">
          {STATS.map((st, i) => (
            <div className={s.stat} key={st.label}>
              <div className={s.statNum}>
                <span
                  ref={(el) => {
                    nums.current[i] = el;
                  }}
                >
                  {run ? '0' : String(st.num)}
                </span>
                <i>{st.unit}</i>
              </div>
              <div className={s.statLabel}>{st.label}</div>
            </div>
          ))}
        </section>

        <section className={s.grid} id="rules" aria-label="能力总览">
          {CARDS.map((c, i) => (
            <article
              key={c.title}
              className={`${s.card} ${s.in}`}
              style={D(`${0.98 + i * 0.08}s`)}
              onMouseMove={spotlight}
            >
              <div className={s.cardTag}>
                <span className={s.cardId}>{c.tag}</span>
                {c.planned ? <span className={s.cardPlanned}>规划中</span> : null}
              </div>
              <h2 className={s.cardTitle}>{c.title}</h2>
              <p className={s.cardBody}>{c.body}</p>
            </article>
          ))}
        </section>

        <section className={`${s.steps} ${s.in}`} style={D('1.35s')} aria-label="使用流程">
          {STEPS.map((st) => (
            <div className={s.step} key={st.n}>
              <span className={s.stepN}>{st.n}</span>
              <b className={s.stepT}>{st.t}</b>
              <span className={s.stepD}>{st.d}</span>
            </div>
          ))}
        </section>
      </main>

      <footer className={s.foot}>
        <span>规则引擎 campus-kb · 19 条规则 · 校验耗时 0.4s</span>
        <span>依据《常用表述规范手册》2026.05 · 数据与出处一一对应</span>
      </footer>
    </div>
  );
}
