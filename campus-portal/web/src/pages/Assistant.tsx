import { useEffect, useRef, useState } from 'react';
import { postAgent, type AgentResult, type ChatTurn } from '../lib/api';
import s from '../styles/assistant.module.css';

type Turn = {
  readonly id: number;
  readonly query: string;
  readonly result?: AgentResult;
  readonly error?: string;
  readonly pending?: boolean;
};

const TOOL_LABEL: Record<string, string> = {
  search_rules: '查规范',
  search_archive: '查档案',
  review_draft: '校稿件',
};

/** 从工具轨迹里挑出给用户看的依据条目（文件名/规则号/命中行）。 */
function cleanAnswer(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/g, '$1') // 去掉模型输出的粗体星号，纯文本展示
    .replace(/^#{1,6}\s+/gm, ''); // 去掉 markdown 标题符号
}

function stepItems(step: AgentResult['steps'][number]): readonly string[] {
  const items = step.result.items ?? [];
  if (step.result.kind === 'rules') {
    return items.slice(0, 4).map((x) => {
      const r = x as { id?: string; desc?: string };
      return r.id ? `[${r.id}] ${r.desc ?? ''}` : (r.desc ?? '—');
    });
  }
  if (step.result.kind === 'archive') {
    return items.slice(0, 4).map((x) => {
      const r = x as { file?: string; line?: number; excerpt?: string };
      return `${r.file ?? ''}${r.line ? ` · 第 ${r.line} 行` : ''}：${r.excerpt ?? ''}`;
    });
  }
  if (step.result.kind === 'review') {
    return items.slice(0, 4).map((x) => {
      const r = x as { ruleId?: string; line?: number; message?: string };
      return `[${r.ruleId ?? ''}] 第 ${r.line ?? ''} 行 · ${r.message ?? ''}`;
    });
  }
  return [];
}

/** 知识库的 Agent 助手：一句话进去，模型自选工具，工具在后端确定性执行。 */
export default function Assistant() {
  const [draft, setDraft] = useState('');
  const [turns, setTurns] = useState<readonly Turn[]>([]);
  const seq = useRef(0);
  const bottom = useRef<HTMLDivElement | null>(null);

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

    // 把本轮之前的对话带进上下文；只取 user/assistant 文本，工具轨迹不入库
    const history: ChatTurn[] = turns.flatMap((t) =>
      t.result
        ? [
            { role: 'user' as const, content: t.query },
            { role: 'assistant' as const, content: t.result.answer },
          ]
        : [],
    );

    try {
      const result = await postAgent(query, history);
      patch(id, { result, pending: false });
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
        <span className={s.barTag}>Agent · 自动检索规则与档案</span>
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
                直接提问即可。助手会自己判断去查规范、查档案还是校稿件，
                <br />
                并展示每一步用了什么工具、依据来自哪里。
              </p>
              <div className={s.suggestList} role="group" aria-label="示例提问">
                {['校名首次出现要注意什么？', '档案里记载了奠基仪式的哪些信息？'].map((q) => (
                  <button
                    type="button"
                    key={q}
                    className={s.suggest}
                    onClick={() => {
                      setDraft(q);
                    }}
                  >
                    {q}
                  </button>
                ))}
              </div>
            </section>
          )}

          <div className={s.threadList} aria-live="polite">
            {turns.map((t) => (
              <div className={s.turn} key={t.id}>
                <div className={s.userMsg}>{t.query}</div>
                {t.pending ? (
                  <div className={s.botMsg}>
                    <span className={s.ansTool}>Agent</span>
                    <p className={s.ansSummary}>正在判断该用哪个工具…</p>
                  </div>
                ) : t.error ? (
                  <div className={s.botMsg}>
                    <p className={s.ansSummary}>查询失败：{t.error}</p>
                    <p className={s.ansEmpty}>请确认本地后端已启动（127.0.0.1:8000）。</p>
                  </div>
                ) : t.result ? (
                  <div className={s.botMsg}>
                    <span className={s.ansTool}>Agent</span>
                    <span className={s.ansAi}>{t.result.model}</span>
                    {t.result.truncated ? (
                      <p className={s.ansTruncated}>本轮工具调用达到上限，结果可能不完整。</p>
                    ) : null}
                    <p className={`${s.ansSummary} ${s.ansAiText}`}>
                      {cleanAnswer(t.result.answer)}
                    </p>

                    {t.result.steps.length > 0 ? (
                      <>
                        <div className={s.ansSrcHead}>执行轨迹</div>
                        <div className={s.stepList}>
                          {t.result.steps.map((step, i) => {
                            const items = stepItems(step);
                            return (
                              <div className={s.step} key={`${step.callId}-${i}`}>
                                <div className={s.stepHead}>
                                  <span className={s.stepIdx}>{i + 1}</span>
                                  <span className={s.stepTool}>
                                    {TOOL_LABEL[step.tool] ?? step.tool}
                                  </span>
                                  <span className={s.stepArgs}>
                                    {Object.values(step.args).join(' · ')}
                                  </span>
                                </div>
                                {items.length > 0 ? (
                                  <div className={s.stepItems}>
                                    {items.map((line, j) => (
                                      <div className={s.stepItem} key={j}>
                                        {line}
                                      </div>
                                    ))}
                                  </div>
                                ) : null}
                                {step.result.kind === 'review' && step.result.counts ? (
                                  <div className={s.stepCount}>
                                    命中 {step.result.counts.total} 项 · 错误{' '}
                                    {step.result.counts.error} / 警告 {step.result.counts.warn}
                                  </div>
                                ) : null}
                              </div>
                            );
                          })}
                        </div>
                      </>
                    ) : (
                      <p className={s.ansNoTool}>本轮未调用工具，直接作答。</p>
                    )}

                    <p className={s.ansAiNote}>
                      由 DeepSeek
                      组织回答；工具结果来自本地知识库与规则引擎，稿件合规性以规则引擎输出为准。
                    </p>
                  </div>
                ) : null}
              </div>
            ))}
            <div ref={bottom} />
          </div>
        </div>
      </div>

      <div className={s.composerWrap}>
        <div className={s.composer}>
          <input
            className={s.input}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void send();
            }}
            placeholder="问规范、查档案、校稿件——直接说就行"
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
        <p className={s.hint}>Agent 自动选择工具 · 校验结论以规则引擎为准</p>
      </div>
    </div>
  );
}
