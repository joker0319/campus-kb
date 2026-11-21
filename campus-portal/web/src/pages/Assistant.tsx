import { useEffect, useRef, useState } from 'react';
import { getRules, postReview, searchArchive, type RulesResult } from '../lib/api';
import {
  answerFromArchive,
  answerFromReview,
  answerFromRules,
  TOOLS,
  type Answer,
  type ToolKind,
} from '../lib/assistantTools';
import s from '../styles/assistant.module.css';

type Turn = {
  readonly id: number;
  readonly query: string;
  readonly answer?: Answer;
  readonly error?: string;
  readonly pending?: boolean;
};

const PLACEHOLDER: Record<ToolKind, string> = {
  rules: '输入规范关键词，如「标点」「序数」「校名」',
  search: '输入档案检索词，多个词用空格分隔',
  review: '粘贴一段正文，检查写作规范',
};

/** 知识库的个人助手：三个确定性工具，逐条给出处，查不到直说。 */
export default function Assistant() {
  const [tool, setTool] = useState<ToolKind>('rules');
  const [draft, setDraft] = useState('');
  const [turns, setTurns] = useState<readonly Turn[]>([]);
  const [rules, setRules] = useState<RulesResult | null>(null);
  const [rulesError, setRulesError] = useState('');
  const seq = useRef(0);
  const bottom = useRef<HTMLDivElement | null>(null);

  // 规则集一次加载，供「问规范」在前端确定性筛选
  useEffect(() => {
    const controller = new AbortController();
    getRules(controller.signal)
      .then(setRules)
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setRulesError(err instanceof Error ? err.message : '规则加载失败');
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: 'end' });
  }, [turns]);

  const patch = (id: number, next: Partial<Turn>) =>
    setTurns((prev) => prev.map((t) => (t.id === id ? { ...t, ...next } : t)));

  const send = async () => {
    const query = draft.trim();
    if (!query || turns.some((t) => t.pending)) return;
    const id = ++seq.current;
    setTurns((prev) => [...prev, { id, query, pending: true }]);
    setDraft('');

    try {
      if (tool === 'rules') {
        if (rulesError || !rules) throw new Error(rulesError || '规则尚未加载完成');
        patch(id, { answer: answerFromRules(query, rules), pending: false });
      } else if (tool === 'search') {
        const res = await searchArchive(query);
        patch(id, { answer: answerFromArchive(query, res), pending: false });
      } else {
        const res = await postReview(query);
        patch(id, { answer: answerFromReview(res), pending: false });
      }
    } catch (err: unknown) {
      patch(id, {
        error: err instanceof Error ? err.message : '调用失败',
        pending: false,
      });
    }
  };

  return (
    <div className={s.page}>
      <header className={s.bar}>
        <a className={s.back} href="#/">
          ← 返回首页
        </a>
        <span className={s.barName}>知识库的个人助手</span>
        <span className={s.barTag}>本地接口 · 逐条给依据</span>
      </header>

      <div className={s.body}>
        <div className={s.thread}>
          {turns.length === 0 && (
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
                选一个工具，我基于 19 条可溯源规则和入库档案回答。
                <br />
                每条都给出处，查不到就直说不知道。
              </p>
            </section>
          )}

          {turns.length === 0 && (
            <div className={s.capList} role="group" aria-label="选择工具">
              {TOOLS.map((c) => (
                <button
                  type="button"
                  key={c.kind}
                  className={`${s.cap} ${c.kind === tool ? s.capActive : ''}`}
                  aria-pressed={c.kind === tool}
                  onClick={() => setTool(c.kind)}
                >
                  <div className={s.capName}>{c.name}</div>
                  <p className={s.capDesc}>{c.desc}</p>
                  <span className={s.capState}>{c.kind === tool ? '已选择' : '可选用'}</span>
                </button>
              ))}
            </div>
          )}

          <div className={s.threadList} aria-live="polite">
            {turns.map((t) => (
              <div className={s.turn} key={t.id}>
                <div className={s.userMsg}>{t.query}</div>
                {t.pending ? (
                  <div className={s.botMsg}>正在查询…</div>
                ) : t.error ? (
                  <div className={s.botMsg}>
                    <p className={s.ansSummary}>查询失败：{t.error}</p>
                    <p className={s.ansEmpty}>请确认本地后端已启动（127.0.0.1:8000）。</p>
                  </div>
                ) : t.answer ? (
                  <div className={s.botMsg}>
                    <span className={s.ansTool}>
                      {TOOLS.find((x) => x.kind === t.answer?.tool)?.name}
                    </span>
                    <p className={s.ansSummary}>{t.answer.summary}</p>
                    {t.answer.items.map((item, i) => (
                      <div className={s.ansItem} key={`${item.meta}-${i}`}>
                        <div className={s.ansTitle}>{item.title}</div>
                        <div className={s.ansMeta}>{item.meta}</div>
                        {item.detail && <div className={s.ansDetail}>{item.detail}</div>}
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
            <div ref={bottom} />
          </div>
        </div>
      </div>

      <div className={s.composerWrap}>
        <div className={s.toolBar} role="group" aria-label="切换工具">
          {TOOLS.map((c) => (
            <button
              type="button"
              key={c.kind}
              className={`${s.toolChip} ${c.kind === tool ? s.toolChipActive : ''}`}
              aria-pressed={c.kind === tool}
              onClick={() => setTool(c.kind)}
            >
              {c.name}
            </button>
          ))}
        </div>
        <div className={s.composer}>
          <input
            className={s.input}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void send();
            }}
            placeholder={PLACEHOLDER[tool]}
            aria-label="助手输入框"
          />
          <button
            className={s.send}
            type="button"
            onClick={() => void send()}
            disabled={!draft.trim() || turns.some((t) => t.pending)}
          >
            发送
          </button>
        </div>
        <p className={s.hint}>确定性工具 · 规则与档案来自本地知识库，不生成臆测内容</p>
      </div>
    </div>
  );
}
