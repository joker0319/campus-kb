import { useEffect, useState } from 'react';
import type { CSSProperties } from 'react';
import { CaseStage } from '../components/CaseStage';
import { PetMascot } from '../components/PetMascot';
import s from '../styles/landing.module.css';

const D = (v: string) => ({ '--d': v }) as CSSProperties;

export default function Landing() {
  /* 入场编排只演一次：结束后摘掉运行态标记，DOM 回到纯静态样式 */
  const [run] = useState(() => !window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const [on, setOn] = useState(run);

  useEffect(() => {
    if (!run) return;
    const t = window.setTimeout(() => setOn(false), 2200);
    return () => window.clearTimeout(t);
  }, [run]);

  return (
    <div className={s.page} data-run={on ? 'true' : 'false'}>
      <div className={s.bg} aria-hidden="true">
        <div className={s.bgAurora} />
        <div className={s.bgGrid} />
        <div className={s.bgNoise} />
      </div>

      {/* 导航栏 */}
      <header className={s.top}>
        <a className={`${s.brand} ${s.in}`} style={D('0s')} href="#/" aria-label="首页">
          <span className={s.brandDot} />
          校园知识库 · 媒体传讯处
        </a>
        <nav className={`${s.nav} ${s.in}`} style={D('.08s')} aria-label="主导航">
          <a href="#/assistant">个人助手</a>
          <a href="#/desk">校稿台</a>
        </nav>
      </header>

      {/* 主体 */}
      <main className={s.main}>
        <section className={s.hero}>
          <div className={s.heroCopy}>
            <p className={`${s.kicker} ${s.in}`} style={D('.06s')}>
              媒体传讯处 · 内容工作台
            </p>
            <h1 className={`${s.title} ${s.in}`} style={D('.14s')}>
              知识库的
              <br />
              个人助手
            </h1>
            <p className={`${s.lede} ${s.in}`} style={D('.24s')}>
              规范、档案与稿件检查，都从一个入口进去。
              <br />
              回答给出处，查不到就直说不知道。
            </p>

            <div className={`${s.petSlot} ${s.in}`} style={D('.36s')}>
              <PetMascot />
            </div>

            <div className={`${s.actions} ${s.in}`} style={D('.46s')}>
              <a className={s.cta} href="#/assistant">
                进入助手 <span className={s.ctaArrow}>→</span>
              </a>
              <a className={s.ctaGhost} href="#/desk">
                去校稿台
              </a>
            </div>
          </div>

          {/* 3D 稿件卡轮播：回到 hero 右栏原位置 */}
          <div className={`${s.heroStage} ${s.in}`} style={D('.3s')}>
            <CaseStage />
          </div>
        </section>
      </main>

      {/* 底部 */}
      <footer className={s.foot}>
        <span>香港城市大学（东莞）· 媒体传讯处</span>
        <span>规则引擎 campus-kb · 19 条可溯源校验规则</span>
      </footer>
    </div>
  );
}
