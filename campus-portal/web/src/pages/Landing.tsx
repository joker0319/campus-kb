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
          RAG 知识库 · 内容助手
        </a>
        <nav className={`${s.nav} ${s.in}`} style={D('.08s')} aria-label="主导航">
          <a href="#/compose">写文章</a>
          <a href="#/assistant">内容助手</a>
          <a href="#/archive">往期推文</a>
          <a href="#/desk">校稿台</a>
        </nav>
      </header>

      {/* 主体 */}
      <main className={s.main}>
        <section className={s.hero}>
          <div className={s.heroCopy}>
            <p className={`${s.kicker} ${s.in}`} style={D('.06s')}>
              RAG 知识库 · Agent 助手
            </p>
            <h1 className={`${s.title} ${s.in}`} style={D('.14s')}>
              写出能发的
              <br />
              公众号文章
            </h1>
            <p className={`${s.lede} ${s.in}`} style={D('.24s')}>
              规范、档案与往期推文都在知识库里，问一句就能用。
              <br />
              回答给出处，查不到就直说不知道。
            </p>

            <div className={`${s.petSlot} ${s.in}`} style={D('.36s')}>
              <PetMascot />
            </div>

            <div className={`${s.actions} ${s.in}`} style={D('.46s')}>
              <a className={s.cta} href="#/compose">
                开始写文章 <span className={s.ctaArrow}>→</span>
              </a>
              <a className={s.ctaGhost} href="#/assistant">
                问问内容助手
              </a>
              <a className={s.ctaGhost} href="#/archive">
                翻往期推文
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
        <span>RAG 知识库 · Agent 助手 · 面向微信公众号内容</span>
        <span>规范与往期推文均可溯源 · 校稿是其中一项能力</span>
      </footer>
    </div>
  );
}
