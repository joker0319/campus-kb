import type { CSSProperties, ReactNode } from 'react';
import type { Counts } from '../types';
import s from '../styles/desk.module.css';
import { IconRefresh } from './icons';

/** 入场延迟透传给 CSS 变量，变量名不在 CSSProperties 类型里，只能断言 */
const delay = (d: string): CSSProperties => ({ '--d': d }) as CSSProperties;

/* ───────────────── 顶栏 ───────────────── */

interface AppBarProps {
  fileName: string;
  onRerun: () => void;
  onExport: () => void;
  onPaste: () => void;
  onUpload: () => void;
  exportLabel: string;
}

export function AppBar({
  fileName,
  onRerun,
  onExport,
  onPaste,
  onUpload,
  exportLabel,
}: AppBarProps) {
  return (
    <header className={`${s.bar} js-anim`} style={delay('0s')}>
      <div className={s.crest}>CITYU</div>
      <a className={s.barName} href="#/" aria-label="返回首页">
        校稿台
      </a>
      <div className={s.barSub}>媒体传讯处</div>
      <div className={s.barSep} />
      <div className={s.docChip}>
        <span className={s.ftype}>DOC</span>
        <b>{fileName}</b>
        <span>待审</span>
      </div>
      <div className={s.barRight}>
        <button className={s.btn} onClick={onPaste} type="button">
          粘贴稿件
        </button>
        <button className={s.btn} onClick={onUpload} type="button">
          上传 docx
        </button>
        <button className={s.btn} onClick={onRerun} type="button">
          <IconRefresh />
          重新校验
        </button>
        <button className={`${s.btn} ${s.btnPrimary}`} onClick={onExport} type="button">
          {exportLabel}
        </button>
        <div className={s.who} title="数据开发">
          数
        </div>
      </div>
    </header>
  );
}

/* ───────────────── 左栏 ───────────────── */

const RAIL = [
  { key: 'review', label: '校稿', icon: 'review' },
  { key: 'library', label: '资源', icon: 'folder' },
  { key: 'rules', label: '条款', icon: 'rules' },
  { key: 'templates', label: '模板', icon: 'template' },
] as const;

export function Rail({
  active = 'review',
  onOpenLibrary,
  libraryOpen = false,
}: {
  active?: string;
  onOpenLibrary?: () => void;
  libraryOpen?: boolean;
}) {
  return (
    <nav className={`${s.rail} js-anim`} style={delay('.04s')} aria-label="主导航">
      {RAIL.map((it) => (
        <button
          key={it.key}
          type="button"
          className={`${s.railItem} ${active === it.key ? s.railOn : ''}`}
          title={it.label}
          aria-current={active === it.key ? 'page' : undefined}
          onClick={it.key === 'library' && onOpenLibrary ? onOpenLibrary : undefined}
          aria-expanded={it.key === 'library' ? libraryOpen : undefined}
        >
          <RailIcon name={it.icon} />
          <span>{it.label}</span>
        </button>
      ))}
      <button type="button" className={`${s.railItem} ${s.railBottom}`} title="设置">
        <RailIcon name="settings" />
        <span>设置</span>
      </button>
    </nav>
  );
}

function RailIcon({ name }: { name: string }) {
  const paths: Record<string, ReactNode> = {
    review: (
      <>
        <path d="M4 4h11l5 5v11H4z" />
        <path d="M9 13l4-4 2 2-4 4H9z" />
        <path d="M15 4v5h5" />
      </>
    ),
    folder: (
      <>
        <path d="M3 7h6l2 2h10v10H3z" />
        <path d="M3 7V5h6" />
      </>
    ),
    rules: (
      <>
        <path d="M5 4h14v16H5z" />
        <path d="M8 8h8M8 12h8M8 16h5" />
      </>
    ),
    template: <path d="M4 4h7v7H4zM13 4h7v4h-7zM13 10h7v10h-7zM4 13h7v7H4z" />,
    settings: (
      <>
        <circle cx="12" cy="12" r="3" />
        <path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9L17 7M7 17l-2.1 2.1" />
      </>
    ),
  };
  return (
    <svg
      width="17"
      height="17"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}

/* ───────────────── 状态栏 ───────────────── */

interface StatusBarProps {
  counts: Counts;
  rulesInEffect: number;
  durationMs: number;
}

export function StatusBar({ counts, rulesInEffect, durationMs }: StatusBarProps) {
  return (
    <footer className={`${s.status} js-anim`} style={delay('.2s')}>
      <span className={s.dotOk} />
      <span>
        校验完成 · <b>{rulesInEffect}</b> 条规则生效
      </span>
      <span className={s.sep} />
      <span>
        命中 <b>{counts.open}</b>&emsp;错误 <b>{counts.error}</b>&emsp;警告 <b>{counts.warning}</b>
      </span>
      <span className={s.sep} />
      <span>
        已忽略 <b>{counts.dismissed}</b>
      </span>
      <span className={s.sp} />
      <span>
        对照组 good-draft.md <b>0</b> 项
      </span>
      <span className={s.sep} />
      <span>
        耗时 <b>{(durationMs / 1000).toFixed(1)}s</b>
      </span>
      <span className={s.sep} />
      <span>规则库 v0.1</span>
    </footer>
  );
}

/* ───────────────── 窄屏标签页 ───────────────── */

export type TabKey = 'doc' | 'issues' | 'evidence';

interface TabsProps {
  tab: TabKey;
  onChange: (t: TabKey) => void;
  counts: Counts;
}

export function MobileTabs({ tab, onChange, counts }: TabsProps) {
  const items: { key: TabKey; label: string; badge?: number }[] = [
    { key: 'doc', label: '稿件' },
    { key: 'issues', label: '问题', badge: counts.open },
    { key: 'evidence', label: '依据' },
  ];
  return (
    <nav className={s.tabs} aria-label="视图切换">
      {items.map((it) => (
        <button
          key={it.key}
          type="button"
          className={`${s.tab} ${tab === it.key ? s.tabOn : ''}`}
          onClick={() => onChange(it.key)}
          aria-current={tab === it.key ? 'page' : undefined}
        >
          {it.label}
          {it.badge ? <span className={s.tabBadge}>{it.badge}</span> : null}
        </button>
      ))}
    </nav>
  );
}
