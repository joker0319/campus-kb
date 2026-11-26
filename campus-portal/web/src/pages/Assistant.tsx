import { useEffect, useRef, useState } from 'react';
import {
  clearAgentMemory,
  streamAgent,
  type AgentResult,
  type AgentStep,
  type ChatTurn,
} from '../lib/api';
import { SoftBackdrop } from '../components/SoftBackdrop';
import s from '../styles/assistant.module.css';

type Turn = {
  readonly id: number;
  readonly query: string;
  readonly result?: AgentResult;
  readonly error?: string;
  readonly pending?: boolean;
  /** 流式过程中已收到的回答文本与工具轨迹，done 后立刻清空 */
  readonly streamText?: string;
  readonly streamSteps?: readonly AgentStep[];
  readonly model?: string;
};

const TOOL_LABEL: Record<string, string> = {
  search_rules: '查规范',
  search_archive: '查档案',
  compare_rule_versions: '比版本',
  archive_timeline: '排时间线',
  review_draft: '校稿件',
};

const SESSION_KEY = 'campus-agent-session';
const TURNS_KEY = 'campus-agent-turns';
const newSessionId = () =>
  `s-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;

/** 会话 ID 与已完成的回合存本地：刷新后 UI 能续上，服务端记忆随后端继续生效。 */
function restoreSession(): string {
  try {
    const saved = localStorage.getItem(SESSION_KEY);
    if (saved && /^[A-Za-z0-9_-]{1,64}$/.test(saved)) return saved;
    const fresh = newSessionId();
    localStorage.setItem(SESSION_KEY, fresh);
    return fresh;
  } catch {
    return newSessionId();
  }
}

function restoreTurns(): readonly Turn[] {
  try {
    const raw = localStorage.getItem(TURNS_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed)
      ? (parsed.filter((t) => t && !t.pending && (t.result || t.error)) as Turn[])
      : [];
  } catch {
    return [];
  }
}

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
  if (step.result.kind === 'versionDiff') {
    const changes = step.result.changes ?? [];
    return changes.slice(0, 4).map((x) => {
      const c = x as { topic?: string; current?: string; old?: readonly string[] };
      return `${c.topic ?? ''}：现行「${c.current ?? ''}」，旧版「${(c.old ?? []).join('、')}」`;
    });
  }
  if (step.result.kind === 'timeline') {
    return items.slice(0, 6).map((x) => {
      const r = x as { date?: string; file?: string; line?: number; excerpt?: string };
      return `${r.date || '无日期'} · ${r.file ?? ''} 第 ${r.line ?? ''} 行：${r.excerpt ?? ''}`;
    });
  }
  return [];
}

/** 工具轨迹：流式过程中与成稿后共用一套展示，避免两处结构漂移。 */
function StepsView({ steps }: { steps: readonly AgentStep[] }) {
  if (steps.length === 0) {
    return <p className={s.ansNoTool}>本轮未调用工具，直接作答。</p>;
  }
  return (
    <>
      <div className={s.ansSrcHead}>执行轨迹</div>
      <div className={s.stepList}>
        {steps.map((step, i) => {
          const items = stepItems(step);
          return (
            <div className={s.step} key={`${step.callId}-${i}`}>
              <div className={s.stepHead}>
                <span className={s.stepIdx}>{i + 1}</span>
                <span className={s.stepTool}>{TOOL_LABEL[step.tool] ?? step.tool}</span>
                <span className={s.stepArgs}>{Object.values(step.args).join(' · ')}</span>
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
                  命中 {step.result.counts.total} 项 · 错误 {step.result.counts.error} / 警告{' '}
                  {step.result.counts.warn}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </>
  );
}

/** 内容助手（Agent）：一句话进去，模型检索知识库自选工具，产出有出处的回答，辅助写公众号文章。 */
export default function Assistant() {
  const [draft, setDraft] = useState('');
  const [sessionId, setSessionId] = useState<string>(restoreSession);
  const [turns, setTurns] = useState<readonly Turn[]>(restoreTurns);
  const seq = useRef(-1);
  if (seq.current === -1) seq.current = turns.reduce((max, t) => Math.max(max, t.id), 0);

  // 已完成的回合落本地，刷新后接着读；正在流式的回合不存，避免半句残留
  useEffect(() => {
    try {
      localStorage.setItem(TURNS_KEY, JSON.stringify(turns.filter((t) => !t.pending)));
    } catch {
      // 隐私模式下 localStorage 不可写，对话仍可正常使用
    }
  }, [turns]);

  // 只在「发出新回合」时滚到该回合顶部，让对话从上往下读；
  // 流式 delta 不再强制置底，否则用户得从底部往上滑才能看到自己发的那条。
  const [scrollToId, setScrollToId] = useState<number | null>(null);

  useEffect(() => {
    if (scrollToId === null) return;
    document.getElementById(`turn-${scrollToId}`)?.scrollIntoView({ block: 'start' });
  }, [scrollToId]);

  const patch = (id: number, next: Partial<Turn>) =>
    setTurns((prev) => prev.map((t) => (t.id === id ? { ...t, ...next } : t)));

  /** 新对话：换会话 ID，本地与服务端记忆一起清掉。 */
  const startNew = async () => {
    const previous = sessionId;
    const fresh = newSessionId();
    setSessionId(fresh);
    setTurns([]);
    try {
      localStorage.setItem(SESSION_KEY, fresh);
      localStorage.removeItem(TURNS_KEY);
      await clearAgentMemory(previous);
    } catch {
      // 后端清理失败只影响旧会话残留，本地新会话已可用
    }
  };

  const send = async () => {
    const query = draft.trim();
    if (!query || turns.some((t) => t.pending)) return;
    const id = ++seq.current;
    setTurns((prev) => [...prev, { id, query, pending: true }]);
    setScrollToId(id);
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
      const result = await streamAgent(
        query,
        history,
        {
          onMeta: (model) => patch(id, { model }),
          onStep: (step) =>
            setTurns((prev) =>
              prev.map((t) =>
                t.id === id ? { ...t, streamSteps: [...(t.streamSteps ?? []), step] } : t,
              ),
            ),
          onDelta: (text) =>
            setTurns((prev) =>
              prev.map((t) =>
                t.id === id ? { ...t, streamText: (t.streamText ?? '') + text } : t,
              ),
            ),
        },
        sessionId,
      );
      patch(id, {
        result,
        pending: false,
        streamText: undefined,
        streamSteps: undefined,
      });
    } catch (err: unknown) {
      patch(id, {
        error: err instanceof Error ? err.message : '调用失败',
        pending: false,
        streamText: undefined,
        streamSteps: undefined,
      });
    }
  };

  return (
    <div className={s.page}>
      <SoftBackdrop />
      <header className={s.bar}>
        <a className={s.back} href="#/">
          ← 返回首页
        </a>
        <span className={s.barName}>内容助手</span>
        <span className={s.barTag}>Agent · 检索知识库，辅助写公众号文章</span>
        <button
          type="button"
          className={s.newChat}
          onClick={() => void startNew()}
          disabled={turns.length === 0 || turns.some((t) => t.pending)}
          title="清空当前对话，开启新会话"
        >
          新对话
        </button>
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
              <h1 className={s.title}>今天写点什么？</h1>
              <p className={s.sub}>
                直接提问即可。助手会从知识库里查规范、查往期推文，
                <br />
                帮你写出能用的公众号文章，并展示依据来自哪里。
              </p>
              <div className={s.suggestList} role="group" aria-label="示例提问">
                {['帮我写一段介绍学校最新科研进展的推文', '档案里记载了奠基仪式的哪些信息？'].map(
                  (q) => (
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
                  ),
                )}
              </div>
            </section>
          )}

          <div className={s.threadList} aria-live="polite">
            {turns.map((t) => (
              <div className={s.turn} id={`turn-${t.id}`} key={t.id}>
                <div className={s.userMsg}>{t.query}</div>
                {t.pending ? (
                  <div className={s.botMsg}>
                    <span className={s.ansTool}>Agent</span>
                    {t.model ? <span className={s.ansAi}>{t.model}</span> : null}
                    {t.streamText ? (
                      <p className={`${s.ansSummary} ${s.ansAiText}`}>
                        {cleanAnswer(t.streamText)}
                        <span className={s.streamCursor} aria-hidden="true" />
                      </p>
                    ) : (
                      <p className={s.ansSummary}>正在判断该用哪个工具…</p>
                    )}
                    {t.streamSteps && t.streamSteps.length > 0 ? (
                      <StepsView steps={t.streamSteps} />
                    ) : null}
                  </div>
                ) : t.error ? (
                  <div className={s.botMsg}>
                    <p className={s.ansSummary}>查询失败：{t.error}</p>
                    <p className={s.ansEmpty}>请确认后端服务正常，或稍后重试。</p>
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

                    <StepsView steps={t.result.steps} />

                    <p className={s.ansAiNote}>
                      由 DeepSeek
                      组织回答；工具结果来自本地知识库与规则引擎，稿件合规性以规则引擎输出为准。
                    </p>
                  </div>
                ) : null}
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
            onKeyDown={(e) => {
              if (e.key === 'Enter') void send();
            }}
            placeholder="说清楚要写什么，或查规范、查档案——直接说就行"
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
        <p className={s.hint}>Agent 自动检索知识库 · 回答给出处，不臆测 · 对话自动保存，刷新可续聊</p>
      </div>
    </div>
  );
}
