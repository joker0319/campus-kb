import { useEffect, useRef, useState } from 'react';
import s from '../styles/search.module.css';

/** GET /api/search 的响应（api/search.py） */
export interface SearchResponse {
  query: string;
  total: number;
  scanned: number;
  results: { file: string; line: number; excerpt: string; hits: number }[];
}

type Phase =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'done'; data: SearchResponse };

/** 档案检索抽屉：调真实接口 /api/search，关键词 → 文件 + 行号 + 摘录 */
export function CorpusSearch({ onClose }: { onClose: () => void }) {
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' });
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const run = async () => {
    const q = inputRef.current?.value.trim() ?? '';
    if (!q) return;
    setPhase({ kind: 'loading' });
    try {
      const r = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
      if (!r.ok) throw new Error(`接口返回 ${r.status}`);
      setPhase({ kind: 'done', data: (await r.json()) as SearchResponse });
    } catch (err) {
      setPhase({
        kind: 'error',
        message: err instanceof Error ? err.message : '检索失败',
      });
    }
  };

  return (
    <aside className={s.wrap} aria-label="档案检索">
      <div className={s.head}>
        <b>档案检索</b>
        <span className={s.hint}>奠基仪式语料 · 26 份</span>
        <button type="button" className={s.close} onClick={onClose} aria-label="关闭检索">
          ✕
        </button>
      </div>

      <form
        className={s.form}
        onSubmit={(e) => {
          e.preventDefault();
          void run();
        }}
      >
        <input
          ref={inputRef}
          className={s.input}
          type="search"
          placeholder="关键词，空格分隔（如：于吉红 奠基）"
          aria-label="检索关键词"
        />
        <button type="submit" className={s.go} disabled={phase.kind === 'loading'}>
          {phase.kind === 'loading' ? '检索中…' : '检索'}
        </button>
      </form>

      <div className={s.body}>
        {phase.kind === 'idle' && <p className={s.muted}>输入关键词检索全部历史档案</p>}
        {phase.kind === 'error' && <p className={s.err}>检索失败：{phase.message}</p>}
        {phase.kind === 'done' && (
          <>
            <p className={s.meta}>
              {phase.data.total > 0
                ? `命中 ${phase.data.total} 行 · 扫描 ${phase.data.scanned} 份`
                : `无结果（扫描 ${phase.data.scanned} 份）`}
            </p>
            <ul className={s.list}>
              {phase.data.results.map((r) => (
                <li key={`${r.file}@${r.line}`} className={s.item}>
                  <div className={s.itemHead}>
                    <span className={s.file}>{r.file}</span>
                    <span className={s.lineNo}>{r.line > 0 ? `第 ${r.line} 行` : ''}</span>
                    <span className={s.hits}>×{r.hits}</span>
                  </div>
                  <p className={s.excerpt}>{r.excerpt}</p>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </aside>
  );
}
