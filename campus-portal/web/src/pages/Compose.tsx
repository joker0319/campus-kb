import { useRef, useState } from 'react';
import { postCompose, postRevise, type ComposeResult, type ComposeSource } from '../lib/api';
import s from '../styles/compose.module.css';

const SUGGESTIONS = [
  '写一篇介绍学校最新科研进展的公众号推文',
  '围绕港城莞 1000 万元捐赠与未来智能中心写一篇推文',
  '根据往期推文，写一篇校园心理健康关怀的文章',
];

const QUICK_EDITS = [
  '标题再短一点',
  '标题更抓人',
  '整体更简洁',
  '把第二部分展开',
  '改成新闻体',
  '语气更温暖',
];

const DRAFTS_KEY = 'campus.drafts.v1';
const MAX_DRAFTS = 5;
const MAX_VERSIONS = 4;

/** 本地草稿：只留最新一版（含素材），版本对比是会话内的能力。 */
interface Draft {
  id: string;
  at: number;
  topic: string;
  result: ComposeResult;
}

function loadDrafts(): Draft[] {
  try {
    const raw = window.localStorage.getItem(DRAFTS_KEY);
    const parsed = raw ? (JSON.parse(raw) as unknown) : null;
    return Array.isArray(parsed) ? (parsed as Draft[]).filter((d) => d && d.result) : [];
  } catch {
    return [];
  }
}

function persistDrafts(list: Draft[]): Draft[] {
  try {
    window.localStorage.setItem(DRAFTS_KEY, JSON.stringify(list));
  } catch {
    // 存满了也不影响出稿：降级为本次会话内可用
  }
  return list;
}

/** 时间戳只在事件回调里取；包一层，避免被当成渲染期调用。 */
function now(): number {
  return Date.now();
}

function newDraftId(): string {
  return `d${now()}`;
}

function timeLabel(at: number): string {
  const d = new Date(at);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getMonth() + 1}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

type State =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'done'; versions: ComposeResult[]; index: number; draftId: string }
  | { kind: 'error'; message: string };

function sourceLine(source: ComposeSource): string {
  return `${source.file}${source.line ? ` · 第 ${source.line} 行` : ''}`;
}

/** 写文章页：选题 → 检索成稿 → 继续改 → 版本回看 → 导出。 */
export default function Compose() {
  const [topic, setTopic] = useState('');
  const [state, setState] = useState<State>({ kind: 'idle' });
  const [copied, setCopied] = useState(false);
  const [instruction, setInstruction] = useState('');
  const [revising, setRevising] = useState(false);
  const [drafts, setDrafts] = useState<Draft[]>(loadDrafts);
  const [showDrafts, setShowDrafts] = useState(false);
  const resultRef = useRef<HTMLDivElement | null>(null);

  const current = state.kind === 'done' ? state.versions[state.index] : null;
  const busy = state.kind === 'loading';

  const generate = async (value: string) => {
    const clean = value.trim();
    if (clean.length < 2) return;
    setState({ kind: 'loading' });
    setCopied(false);
    setInstruction('');
    resultRef.current?.scrollIntoView({ block: 'start', behavior: 'smooth' });
    try {
      const result = await postCompose(clean);
      const draftId = newDraftId();
      setState({ kind: 'done', versions: [result], index: 0, draftId });
      setDrafts((prev) =>
        persistDrafts(
          [{ id: draftId, at: now(), topic: clean, result }, ...prev].slice(0, MAX_DRAFTS),
        ),
      );
    } catch (err: unknown) {
      setState({
        kind: 'error',
        message: err instanceof Error ? err.message : '生成失败，请稍后重试',
      });
    }
  };

  const revise = async (text: string) => {
    if (state.kind !== 'done') return;
    const clean = text.trim();
    if (!clean) return;
    const base = state.versions[state.index];
    if (!base) return;
    setRevising(true);
    try {
      const next = await postRevise({
        topic: base.topic,
        instruction: clean,
        article: base.article,
        sources: base.sources,
        rules: base.rules,
      });
      const versions = [...state.versions.slice(0, state.index + 1), next].slice(-MAX_VERSIONS);
      const index = versions.length - 1;
      setState({ kind: 'done', versions, index, draftId: state.draftId });
      setDrafts((prev) =>
        prev.map((d) => (d.id === state.draftId ? { ...d, at: now(), result: next } : d)),
      );
      setInstruction('');
    } catch (err: unknown) {
      setState({
        kind: 'error',
        message: err instanceof Error ? err.message : '改稿失败，请稍后重试',
      });
    } finally {
      setRevising(false);
    }
  };

  const openDraft = (d: Draft) => {
    setTopic(d.topic);
    setInstruction('');
    setShowDrafts(false);
    setState({ kind: 'done', versions: [d.result], index: 0, draftId: d.id });
    window.setTimeout(
      () => resultRef.current?.scrollIntoView({ block: 'start', behavior: 'smooth' }),
      0,
    );
  };

  const removeDraft = (id: string) => {
    setDrafts((prev) => persistDrafts(prev.filter((d) => d.id !== id)));
  };

  const copyMarkdown = async () => {
    if (!current) return;
    try {
      await navigator.clipboard.writeText(current.markdown);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  const downloadMarkdown = () => {
    if (!current) return;
    const blob = new Blob([current.markdown], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${current.article.title || '公众号文章草稿'}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className={s.page}>
      <header className={s.bar}>
        <a className={s.back} href="#/">
          ← 返回首页
        </a>
        <span className={s.barName}>写文章</span>
        <button
          type="button"
          className={s.draftBtn}
          onClick={() => setShowDrafts((v) => !v)}
          aria-expanded={showDrafts}
        >
          草稿箱{drafts.length > 0 ? ` · ${drafts.length}` : ''}
        </button>
        <span className={s.barTag}>RAG 知识库 · Agent 成稿 · 出处可溯</span>
      </header>

      <main className={s.body}>
        <div className={s.panel}>
          <div className={s.head}>
            <p className={s.kicker}>CONTENT STUDIO</p>
            <h1 className={s.title}>把选题写成能发的文章</h1>
            <p className={s.lede}>
              助手从规范、档案与往期推文中检索素材，据此写成公众号草稿。
              <br />
              不满意就直接说怎么改，它会在原稿上改，不重新编素材。
            </p>
          </div>

          {showDrafts && (
            <div className={s.drafts}>
              <div className={s.draftsHead}>
                <span>本地草稿</span>
                <span className={s.draftsHint}>保存在这台设备，刷新不丢</span>
              </div>
              {drafts.length === 0 && <p className={s.draftsEmpty}>还没有草稿，先写一篇。</p>}
              {drafts.map((d) => (
                <div className={s.draftItem} key={d.id}>
                  <button type="button" className={s.draftOpen} onClick={() => openDraft(d)}>
                    <span className={s.draftTopic}>{d.topic}</span>
                    <span className={s.draftMeta}>{timeLabel(d.at)}</span>
                  </button>
                  <button
                    type="button"
                    className={s.draftDel}
                    onClick={() => removeDraft(d.id)}
                    aria-label={`删除草稿 ${d.topic}`}
                  >
                    删除
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className={s.inputCard}>
            <label className={s.label} htmlFor="compose-topic">
              文章选题 / 写作要求
            </label>
            <textarea
              id="compose-topic"
              className={s.input}
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) void generate(topic);
              }}
              placeholder="例如：写一篇介绍学校最新科研进展的推文，突出产学研融合"
              aria-label="文章选题输入框"
            />
            <div className={s.row}>
              <button
                type="button"
                className={s.generate}
                disabled={busy || topic.trim().length < 2}
                onClick={() => void generate(topic)}
              >
                {busy ? '正在检索并成稿…' : '生成文章'}
              </button>
              <span className={s.hint}>⌘/Ctrl + Enter 快速生成</span>
            </div>
            <div className={s.suggestRow}>
              {SUGGESTIONS.map((tip) => (
                <button
                  type="button"
                  key={tip}
                  className={s.suggest}
                  disabled={busy}
                  onClick={() => {
                    setTopic(tip);
                    void generate(tip);
                  }}
                >
                  {tip}
                </button>
              ))}
            </div>
          </div>

          {state.kind === 'error' && (
            <div className={s.error} role="alert">
              {state.message}
            </div>
          )}

          {state.kind === 'done' && current && (
            <div className={s.result} ref={resultRef}>
              <div className={s.resultBar}>
                <span className={s.resultTitle}>草稿预览</span>
                <span
                  className={`${s.badge} ${current.citations.grounded ? s.badgeOk : s.badgeWarn}`}
                >
                  {current.citations.grounded
                    ? '全部段落有出处'
                    : `${current.citations.uncitedParagraphs} 段待补充`}
                </span>
                <span
                  className={`${s.badge} ${current.review.counts.error === 0 ? s.badgeOk : s.badgeWarn}`}
                >
                  规范检查 {current.review.counts.error} 错 / {current.review.counts.warn} 警
                </span>
                <span className={s.spacer} />
                <button type="button" className={s.copyBtn} onClick={() => void copyMarkdown()}>
                  {copied ? '已复制' : '复制 Markdown'}
                </button>
                <button type="button" className={s.downloadBtn} onClick={downloadMarkdown}>
                  下载 .md
                </button>
              </div>

              {state.versions.length > 1 && (
                <div className={s.versionBar}>
                  <span className={s.versionLabel}>版本</span>
                  {state.versions.map((_, i) => (
                    <button
                      type="button"
                      key={i}
                      className={`${s.versionBtn} ${i === state.index ? s.versionOn : ''}`}
                      onClick={() =>
                        setState((prev) => (prev.kind === 'done' ? { ...prev, index: i } : prev))
                      }
                    >
                      v{i + 1}
                    </button>
                  ))}
                  <span className={s.versionHint}>
                    {state.index < state.versions.length - 1
                      ? '正在看历史版本，继续改会从这里分叉'
                      : '最新一版'}
                  </span>
                </div>
              )}

              <article className={s.article}>
                {current.article.title && (
                  <h2 className={s.articleTitle}>{current.article.title}</h2>
                )}
                {current.article.lead && <p className={s.lead}>{current.article.lead}</p>}

                {current.article.sections.map((sec, si) => (
                  <section className={s.sec} key={`${si}-${sec.heading}`}>
                    {sec.heading && <h3 className={s.secHeading}>{sec.heading}</h3>}
                    {sec.paragraphs.map((p, pi) => {
                      const isPlaceholder = p.text.startsWith('（素材不足');
                      return (
                        <p className={`${s.para} ${isPlaceholder ? s.placeholder : ''}`} key={pi}>
                          {p.text}
                          {p.cites.map((c) => (
                            <span className={s.cite} key={c}>
                              [{c}]
                            </span>
                          ))}
                        </p>
                      );
                    })}
                  </section>
                ))}

                {current.article.imageSuggestions.length > 0 && (
                  <div className={s.images}>
                    <p className={s.imagesHead}>配图建议</p>
                    {current.article.imageSuggestions.map((im, i) => (
                      <p className={s.imageItem} key={i}>
                        {im.after && `${im.after}：`}
                        {im.description}
                      </p>
                    ))}
                  </div>
                )}
              </article>

              <div className={s.revise}>
                <div className={s.reviseHead}>
                  <span className={s.reviseTitle}>继续改</span>
                  <span className={s.reviseHint}>只改你点名的部分，素材编号不变</span>
                </div>
                <div className={s.reviseChips}>
                  {QUICK_EDITS.map((q) => (
                    <button
                      type="button"
                      key={q}
                      className={s.reviseChip}
                      disabled={revising}
                      onClick={() => void revise(q)}
                    >
                      {q}
                    </button>
                  ))}
                </div>
                <div className={s.reviseRow}>
                  <input
                    className={s.reviseInput}
                    value={instruction}
                    onChange={(e) => setInstruction(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') void revise(instruction);
                    }}
                    placeholder="例如：第三段太长，压缩到两句话"
                    aria-label="修改要求输入框"
                    disabled={revising}
                  />
                  <button
                    type="button"
                    className={s.reviseBtn}
                    disabled={revising || !instruction.trim()}
                    onClick={() => void revise(instruction)}
                  >
                    {revising ? '修改中…' : '按这条改'}
                  </button>
                </div>
              </div>

              <div className={s.disclosures}>
                <details className={s.disclosure}>
                  <summary className={s.dSummary}>
                    事实依据 · {current.citations.cited.length} 条素材被引用
                  </summary>
                  <div className={s.dBody}>
                    {current.citations.invalidCites.length > 0 && (
                      <p className={s.findingItem}>
                        无效引用：{current.citations.invalidCites.join('、')}
                      </p>
                    )}
                    {current.citations.cited.length === 0 && (
                      <p className={s.empty}>没有段落引用到素材，请检查选题或更换表述。</p>
                    )}
                    {current.citations.cited.map((src) => (
                      <p className={s.sourceItem} key={src.ref}>
                        <span className={s.sourceRef}>[{src.ref}]</span>
                        {src.text}
                        <span className={s.sourceFile}> — {sourceLine(src)}</span>
                      </p>
                    ))}
                  </div>
                </details>

                <details className={s.disclosure}>
                  <summary className={s.dSummary}>
                    发前检查 · 规范命中 {current.review.findings.length} 项
                  </summary>
                  <div className={s.dBody}>
                    {current.review.findings.length === 0 && (
                      <p className={s.empty}>规则引擎未发现问题。</p>
                    )}
                    {current.review.findings.map((f, i) => (
                      <p
                        className={`${s.findingItem} ${f.severity === 'error' ? s.findingError : s.findingWarn}`}
                        key={i}
                      >
                        [{f.ruleId}] 第 {f.line} 行 · {f.message}
                        {f.suggestion && ` → ${f.suggestion}`}
                      </p>
                    ))}
                  </div>
                </details>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
