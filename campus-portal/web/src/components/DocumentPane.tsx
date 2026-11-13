import { useEffect, useRef, useState } from 'react';
import type { CSSProperties } from 'react';
import type { Draft, Issue } from '../types';
import { severityOfKeys, validKeys } from '../lib/review';
import s from '../styles/desk.module.css';

const delay = (d: string): CSSProperties => ({ '--d': d }) as CSSProperties;

interface Props {
  draft: Draft;
  issueMap: ReadonlyMap<string, Issue>;
  showMarks: boolean;
  selectedKey: string | null;
  /** 选中的问题所在行；配合 scrollToken 触发滚动 + 闪烁 */
  focusLine: number | null;
  scrollToken: number;
  onPickMark: (key: string) => void;
  onToggleMarks: (on: boolean) => void;
}

export function DocumentPane({
  draft,
  issueMap,
  showMarks,
  selectedKey,
  focusLine,
  scrollToken,
  onPickMark,
  onToggleMarks,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [flashLine, setFlashLine] = useState<number | null>(null);

  // scrollToken 每次主动定位自增，effect 只在「用户点了一条问题」时跑
  useEffect(() => {
    if (scrollToken === 0 || focusLine === null) return;
    const el = scrollRef.current?.querySelector<HTMLParagraphElement>(
      `p[data-line="${focusLine}"]`,
    );
    if (!el) return;
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    setFlashLine(focusLine);
    const timer = window.setTimeout(() => setFlashLine(null), 1100);
    return () => window.clearTimeout(timer);
  }, [scrollToken, focusLine]);

  return (
    <main
      className={`${s.doc} js-anim`}
      style={delay('.08s')}
      ref={scrollRef}
      aria-label="稿件正文"
    >
      <div className={s.docHead}>
        <span className={s.dhT}>稿件正文</span>
        <div className={s.dhR}>
          <label className={s.switch}>
            <input
              type="checkbox"
              checked={showMarks}
              onChange={(e) => onToggleMarks(e.target.checked)}
            />
            显示标记
          </label>
        </div>
      </div>

      <div className={s.sheet}>
        <div className={s.sheetMeta}>
          <span>
            送审 <b>2026-11-11 21:20</b>
          </span>
          <span className={s.sp} />
          <span>
            报送模板 <b>通讯新闻报送模板 250324</b>
          </span>
          <span>
            正文 <b>512</b> 字
          </span>
        </div>

        <div className={`${s.prose} ${showMarks ? '' : s.plain}`}>
          {draft.map((para) => (
            <p
              key={para.line}
              data-line={para.line}
              className={[para.isTitle ? s.paraTitle : '', flashLine === para.line ? s.flash : '']
                .filter(Boolean)
                .join(' ')}
            >
              <span className={s.ln}>{para.line}</span>
              {para.segments.map((seg, i) => {
                const keys = validKeys(seg.issueKeys, issueMap);
                if (keys.length === 0) return <span key={i}>{seg.text}</span>;

                const severity = severityOfKeys(keys, issueMap);
                const isOn = selectedKey !== null && keys.includes(selectedKey);
                const cls = [s.mk, severity === 'warning' ? s.mkW : '', isOn ? s.mkOn : '']
                  .filter(Boolean)
                  .join(' ');

                return (
                  <span
                    key={i}
                    className={cls}
                    role="button"
                    tabIndex={showMarks ? 0 : -1}
                    title={`${keys.length} 条问题 · 点击查看依据`}
                    onClick={() => showMarks && onPickMark(keys[0]!)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        onPickMark(keys[0]!);
                      }
                    }}
                  >
                    {seg.text}
                  </span>
                );
              })}
            </p>
          ))}
        </div>
      </div>
    </main>
  );
}
