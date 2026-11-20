import { useState } from 'react';
import s from '../styles/assistant.module.css';

const CAPABILITIES = [
  { name: '问规范', desc: '校名、职务、港澳台表述与标点格式，逐条给依据。' },
  { name: '查档案', desc: '在入库档案里做全文检索，返回文件与行号。' },
  { name: '校稿件', desc: '粘一段正文，命中处标红并给出改法。' },
] as const;

/** 助手页壳：先交付界面与入口，工具调用后续接入。不臆测、不伪装回答。 */
export default function Assistant() {
  const [draft, setDraft] = useState('');

  return (
    <div className={s.page}>
      <header className={s.bar}>
        <a className={s.back} href="#/">
          ← 返回首页
        </a>
        <span className={s.barName}>知识库的个人助手</span>
        <span className={s.barTag}>界面预览 · 能力待接入</span>
      </header>

      <div className={s.body}>
        <div className={s.thread}>
          <section className={s.intro}>
            <div className={s.mark} aria-hidden="true">
              <svg viewBox="10 6 44 54" width="56" height="56">
                <path
                  fill="var(--ink)"
                  d="M32 22c8.2 0 15.2 7 16.4 17C49.6 49 41.4 57 32 57S14.4 49 15.6 39C16.8 29 23.8 22 32 22Z"
                />
                <ellipse fill="var(--surface)" cx="25.6" cy="37" rx="5.1" ry="5.7" />
                <ellipse fill="var(--surface)" cx="38.4" cy="37" rx="5.1" ry="5.7" />
                <circle fill="var(--ink)" cx="25.6" cy="37.6" r="2.35" />
                <circle fill="var(--ink)" cx="38.4" cy="37.6" r="2.35" />
              </svg>
            </div>
            <h1 className={s.title}>有什么可以帮你？</h1>
            <p className={s.sub}>
              我是媒体传讯处知识库的个人助手。下面三项能力正在接入，
              <br />
              现在可先去校稿台体验真实的规范校验。
            </p>
          </section>

          <div className={s.welcome}>
            <span className={s.welcomeAvatar} aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="var(--surface)" strokeWidth="2">
                <path d="M5 12h14M13 6l6 6-6 6" />
              </svg>
            </span>
            <p className={s.welcomeText}>
              你好。我能基于 19
              条可溯源规则和入库档案回答问题，回答会给出处，查不到就直说不知道。工具接入完成后即可在这里对话。
            </p>
          </div>

          <div className={s.capList}>
            {CAPABILITIES.map((c) => (
              <div className={s.cap} key={c.name}>
                <div className={s.capName}>{c.name}</div>
                <p className={s.capDesc}>{c.desc}</p>
                <span className={s.capState}>接入中</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className={s.composerWrap}>
        <div className={s.composer}>
          <input
            className={s.input}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="能力接入后可在这里提问"
            aria-label="助手输入框"
            disabled
          />
          <button className={s.send} type="button" disabled>
            发送
          </button>
        </div>
        <p className={s.hint}>界面预览 · 发送功能将在工具接入后开放，暂不生成任何回答</p>
      </div>
    </div>
  );
}
