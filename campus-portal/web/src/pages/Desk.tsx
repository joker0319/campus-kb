import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { DRAFT, ISSUES, RULES } from '../data/content';
import { buildIssueMap } from '../lib/review';
import { useReview } from '../hooks/useReview';
import { useMediaQuery } from '../hooks/useMediaQuery';
import { AppBar, MobileTabs, Rail, StatusBar } from '../components/Shell';
import { CorpusSearch } from '../components/CorpusSearch';
import { DocumentPane } from '../components/DocumentPane';
import { IssueList } from '../components/IssueList';
import { EvidencePane } from '../components/EvidencePane';
import s from '../styles/desk.module.css';

/** 引擎实际生效规则数（campus-kb 19 条）；RULES 只收录被命中过的规则定义 */
const RULES_IN_EFFECT = 19;
const ENGINE_MS = 400;

const RULE_MAP = new Map(RULES.map((r) => [r.id, r]));

/** B 类工作台页面：无渐变、无光斑，动效只有一次 420ms 分层落位 */
export default function Desk() {
  const issueMap = useMemo(() => buildIssueMap(ISSUES), []);
  const { state, counts, visible, selected, dispatch, select, step } = useReview(ISSUES);

  const wide = useMediaQuery('(min-width: 1181px)');
  const compact = useMediaQuery('(max-width: 900px)');

  const [tab, setTab] = useState<'doc' | 'issues' | 'evidence'>('doc');
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [exportLabel, setExportLabel] = useState('导出批注');
  const exportTimer = useRef<number | null>(null);

  // 一次性入场：动画跑完就摘掉标记，元素回落到默认可见样式
  useEffect(() => {
    const t = window.setTimeout(() => document.documentElement.classList.remove('motion-run'), 900);
    return () => window.clearTimeout(t);
  }, []);

  useEffect(
    () => () => {
      if (exportTimer.current !== null) window.clearTimeout(exportTimer.current);
    },
    [],
  );

  const goStep = useCallback(
    (dir: 1 | -1) => {
      step(dir);
      if (compact) setTab('issues');
    },
    [step, compact],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable))
        return;

      if (e.key === 'Escape') {
        select(null);
        return;
      }
      const down = e.key === 'j' || e.key === 'ArrowDown';
      const up = e.key === 'k' || e.key === 'ArrowUp';
      if (!down && !up) return;
      e.preventDefault();
      goStep(down ? 1 : -1);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [goStep, select]);

  const onExport = () => {
    setExportLabel(`已生成 · ${counts.total} 条批注`);
    if (exportTimer.current !== null) window.clearTimeout(exportTimer.current);
    exportTimer.current = window.setTimeout(() => setExportLabel('导出批注'), 1600);
  };

  const onRerun = () => {
    dispatch({ type: 'reset' });
    setExportLabel('导出批注');
  };

  const rule = selected ? (RULE_MAP.get(selected.ruleId) ?? null) : null;
  const focusLine = selected?.line ?? null;

  const wsClass = compact ? s.workspaceCompact : wide ? s.workspace : s.workspaceNoEvidence;

  const docPane = (
    <DocumentPane
      draft={DRAFT}
      issueMap={issueMap}
      showMarks={state.showMarks}
      selectedKey={state.selectedKey}
      focusLine={focusLine}
      scrollToken={state.scrollToken}
      onPickMark={(key) => select(key, true)}
      onToggleMarks={(on) => dispatch({ type: 'marks', on })}
    />
  );

  const issuePane = (
    <IssueList
      issues={visible}
      counts={counts}
      filter={state.filter}
      selectedKey={state.selectedKey}
      onFilter={(f) => dispatch({ type: 'filter', filter: f })}
      onSelect={(key) => {
        select(key, true);
        if (compact) setTab('doc');
      }}
      onDismiss={(key) => dispatch({ type: 'toggle', key })}
    />
  );

  const evidencePane = <EvidencePane issue={selected} rule={rule} />;

  return (
    <div className={`${s.app} ${compact ? s.appCompact : ''}`}>
      <AppBar
        fileName="bad-draft.md"
        onRerun={onRerun}
        onExport={onExport}
        exportLabel={exportLabel}
      />

      <div className={wsClass}>
        <Rail onOpenLibrary={() => setLibraryOpen((v) => !v)} libraryOpen={libraryOpen} />
        {libraryOpen ? <CorpusSearch onClose={() => setLibraryOpen(false)} /> : null}
        {compact ? (
          <>
            {tab === 'doc' && docPane}
            {tab === 'issues' && issuePane}
            {tab === 'evidence' && evidencePane}
          </>
        ) : (
          <>
            {docPane}
            {issuePane}
            {wide ? evidencePane : null}
          </>
        )}
      </div>

      {compact ? (
        <MobileTabs tab={tab} onChange={setTab} counts={counts} />
      ) : (
        <StatusBar counts={counts} rulesInEffect={RULES_IN_EFFECT} durationMs={ENGINE_MS} />
      )}

      {/* 中等宽度：依据收成底部抽屉，选中问题即展开 */}
      {!wide && !compact ? (
        <div
          className={`${s.sheetWrap} ${selected ? s.sheetWrapOpen : ''}`}
          aria-hidden={!selected}
        >
          <div className={s.sheetHandle}>
            <span className={s.grab} />
            <span>判定依据</span>
            {rule ? (
              <span style={{ color: 'var(--ink-2)' }}>
                · {rule.id} {rule.name}
              </span>
            ) : null}
            <button type="button" onClick={() => select(null)}>
              收起
            </button>
          </div>
          <EvidencePane issue={selected} rule={rule} headless />
        </div>
      ) : null}
    </div>
  );
}
