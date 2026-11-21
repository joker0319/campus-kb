import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { RULES } from '../data/content';
import { buildIssueMap } from '../lib/review';
import { useReview } from '../hooks/useReview';
import { useReviewRequest } from '../hooks/useReviewRequest';
import { useMediaQuery } from '../hooks/useMediaQuery';
import { AppBar, MobileTabs, Rail, StatusBar } from '../components/Shell';
import { CorpusSearch } from '../components/CorpusSearch';
import { SubmitDialog } from '../components/SubmitDialog';
import { DocumentPane } from '../components/DocumentPane';
import { IssueList } from '../components/IssueList';
import { EvidencePane } from '../components/EvidencePane';
import s from '../styles/desk.module.css';
import type { Issue } from '../types';

const NO_ISSUES: readonly Issue[] = [];
const RULE_MAP = new Map(RULES.map((r) => [r.id, r]));

/** B 类工作台页面：无渐变、无光斑，动效只有一次 420ms 分层落位 */
export default function Desk() {
  const { phase, sourceKind, displayName, draft, report, reportName, submit, submitFile, retry } =
    useReviewRequest();
  const issues = phase.kind === 'ready' ? phase.result.issues : NO_ISSUES;
  const issueMap = useMemo(() => buildIssueMap(issues), [issues]);
  const { state, counts, visible, selected, dispatch, select, step } = useReview(issues);

  const wide = useMediaQuery('(min-width: 1181px)');
  const compact = useMediaQuery('(max-width: 900px)');

  const [tab, setTab] = useState<'doc' | 'issues' | 'evidence'>('doc');
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [pasteOpen, setPasteOpen] = useState(false);
  const [exportLabel, setExportLabel] = useState('导出批注');
  const exportTimer = useRef<number | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

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

  /** 有 Markdown 报告（docx 上传路径）时真正下载，否则保留占位提示 */
  const onExport = () => {
    if (report) {
      const blob = new Blob([report], { type: 'text/markdown;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${reportName.replace(/\.docx$/i, '') || '稿件'}.md`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setExportLabel(`已下载 · ${counts.total} 条批注`);
    } else {
      setExportLabel(`已生成 · ${counts.total} 条批注`);
    }
    if (exportTimer.current !== null) window.clearTimeout(exportTimer.current);
    exportTimer.current = window.setTimeout(() => setExportLabel('导出批注'), 1600);
  };

  const onPickFile = () => fileRef.current?.click();

  const onRerun = () => {
    dispatch({ type: 'reset' });
    setExportLabel('导出批注');
    retry();
  };

  const rule = selected ? (RULE_MAP.get(selected.ruleId) ?? null) : null;
  const focusLine = selected?.line ?? null;

  const wsClass = compact ? s.workspaceCompact : wide ? s.workspace : s.workspaceNoEvidence;

  const docPane = (
    <DocumentPane
      draft={draft}
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
      <input
        ref={fileRef}
        type="file"
        className={s.fileInput}
        accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        aria-label="上传 docx 文件"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) {
            dispatch({ type: 'reset' });
            setExportLabel('导出批注');
            submitFile(file);
          }
          // 允许再次选同一份文件
          e.target.value = '';
        }}
      />

      <AppBar
        fileName={displayName}
        onRerun={onRerun}
        onPaste={() => setPasteOpen(true)}
        onUpload={onPickFile}
        onExport={onExport}
        exportLabel={exportLabel}
      />

      {phase.kind === 'loading' ? (
        <div className={s.notice} role="status">
          {sourceKind === 'file' ? '正在提取 docx 正文并校验…' : '正在调用校验接口…'}
        </div>
      ) : null}
      {phase.kind === 'error' ? (
        <div className={`${s.notice} ${s.noticeErr}`} role="alert">
          校验接口不可用：{phase.message}
          <button type="button" onClick={retry}>
            重试
          </button>
        </div>
      ) : null}

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
        <StatusBar
          counts={counts}
          rulesInEffect={phase.kind === 'ready' ? phase.result.ruleCount : 0}
          durationMs={phase.kind === 'ready' ? phase.result.durationMs : 0}
        />
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

      {pasteOpen ? (
        <SubmitDialog
          onClose={() => setPasteOpen(false)}
          onSubmit={(text) => {
            dispatch({ type: 'reset' });
            submit(text);
            setPasteOpen(false);
          }}
        />
      ) : null}
    </div>
  );
}
