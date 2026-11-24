import { useRef, useState } from 'react';
import { postCompose, type ComposeResult, type ComposeSource } from '../lib/api';
import s from '../styles/compose.module.css';

const SUGGESTIONS = [
  '写一篇介绍学校最新科研进展的公众号推文',
  '围绕港城莞 1000 万元捐赠与未来智能中心写一篇推文',
  '根据往期推文，写一篇校园心理健康关怀的文章',
];

type State =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'done'; result: ComposeResult }
  | { kind: 'error'; message: string };

function sourceLine(source: ComposeSource): string {
  return `${source.file}${source.line ? ` · 第 ${source.line} 行` : ''}`;
}

/** 写文章页：输入选题 → 检索知识库成稿 → 展示可溯源草稿并导出。 */
export default function Compose() {
  const [topic, setTopic] = useState('');
  const [state, setState] = useState<State>({ kind: 'idle' });
  const [copied, setCopied] = useState(false);
  const resultRef = useRef<HTMLDivElement | null>(null);

  const generate = async (value: string) => {
    const clean = value.trim();
    if (clean.length < 2) return;
    setState({ kind: 'loading' });
    setCopied(false);
    resultRef.current?.scrollIntoView({ block: 'start', behavior: 'smooth' });
    try {
      const result = await postCompose(clean);
      setState({ kind: 'done', result });
    } catch (err: unknown) {
      setState({
        kind: 'error',
        message: err instanceof Error ? err.message : '生成失败，请稍后重试',
      });
    }
  };

  const copyMarkdown = async () => {
    if (state.kind !== 'done') return;
    try {
      await navigator.clipboard.writeText(state.result.markdown);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  const downloadMarkdown = () => {
    if (state.kind !== 'done') return;
    const blob = new Blob([state.result.markdown], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${state.result.article.title || '公众号文章草稿'}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const busy = state.kind === 'loading';

  return (
    <div className={s.page}>
      <header className={s.bar}>
        <a className={s.back} href="#/">
          ← 返回首页
        </a>
        <span className={s.barName}>写文章</span>
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
              每段都带出处；查不到依据的地方会明确标注，不臆测。
            </p>
          </div>

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

          {state.kind === 'done' && (
            <div className={s.result} ref={resultRef}>
              <div className={s.resultBar}>
                <span className={s.resultTitle}>草稿预览</span>
                <span
                  className={`${s.badge} ${state.result.citations.grounded ? s.badgeOk : s.badgeWarn}`}
                >
                  {state.result.citations.grounded
                    ? '全部段落有出处'
                    : `${state.result.citations.uncitedParagraphs} 段待补充`}
                </span>
                <span
                  className={`${s.badge} ${state.result.review.counts.error === 0 ? s.badgeOk : s.badgeWarn}`}
                >
                  规范检查 {state.result.review.counts.error} 错 / {state.result.review.counts.warn}{' '}
                  警
                </span>
                <span className={s.spacer} />
                <button type="button" className={s.copyBtn} onClick={() => void copyMarkdown()}>
                  {copied ? '已复制' : '复制 Markdown'}
                </button>
                <button type="button" className={s.downloadBtn} onClick={downloadMarkdown}>
                  下载 .md
                </button>
              </div>

              <article className={s.article}>
                {state.result.article.title && (
                  <h2 className={s.articleTitle}>{state.result.article.title}</h2>
                )}
                {state.result.article.lead && <p className={s.lead}>{state.result.article.lead}</p>}

                {state.result.article.sections.map((sec, si) => (
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

                {state.result.article.imageSuggestions.length > 0 && (
                  <div className={s.images}>
                    <p className={s.imagesHead}>配图建议</p>
                    {state.result.article.imageSuggestions.map((im, i) => (
                      <p className={s.imageItem} key={i}>
                        {im.after && `${im.after}：`}
                        {im.description}
                      </p>
                    ))}
                  </div>
                )}
              </article>

              <div className={s.disclosures}>
                <details className={s.disclosure}>
                  <summary className={s.dSummary}>
                    事实依据 · {state.result.citations.cited.length} 条素材被引用
                  </summary>
                  <div className={s.dBody}>
                    {state.result.citations.invalidCites.length > 0 && (
                      <p className={s.findingItem}>
                        无效引用：{state.result.citations.invalidCites.join('、')}
                      </p>
                    )}
                    {state.result.citations.cited.length === 0 && (
                      <p className={s.empty}>没有段落引用到素材，请检查选题或更换表述。</p>
                    )}
                    {state.result.citations.cited.map((src) => (
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
                    发前检查 · 规范命中 {state.result.review.findings.length} 项
                  </summary>
                  <div className={s.dBody}>
                    {state.result.review.findings.length === 0 && (
                      <p className={s.empty}>规则引擎未发现问题。</p>
                    )}
                    {state.result.review.findings.map((f, i) => (
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
