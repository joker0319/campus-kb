import { useCallback, useEffect, useState } from 'react';
import { DRAFT, DRAFT_TEXT } from '../data/content';
import { buildDraft } from '../lib/buildDraft';
import { postReview, reviewFile, type ReviewResult } from '../lib/api';
import type { Draft } from '../types';

export type ReviewPhase =
  | { kind: 'loading' }
  | { kind: 'ready'; result: ReviewResult }
  | { kind: 'error'; message: string };

/** 送审来源：粘贴正文走 /api/review，docx 文件走 /api/review-file */
type Source = { kind: 'text'; text: string } | { kind: 'file'; file: File };

/** 当前送审内容、展示名与校验结果；submit/submitFile 可换稿。 */
export function useReviewRequest() {
  const [phase, setPhase] = useState<ReviewPhase>({ kind: 'loading' });
  const [source, setSource] = useState<Source>({ kind: 'text', text: DRAFT_TEXT });
  const [content, setContent] = useState(DRAFT_TEXT);
  const [displayName, setDisplayName] = useState('bad-draft.md');
  const [draft, setDraft] = useState<Draft>(DRAFT);
  const [report, setReport] = useState<string | null>(null);
  const [reportName, setReportName] = useState('');
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    const controller = new AbortController();

    // 两条路径统一成同一种结果，下面的 then 不需要区分来源
    const task =
      source.kind === 'text'
        ? postReview(source.text, 'submission', controller.signal).then((result) => ({
            result,
            text: source.text,
            report: null as string | null,
            reportName: '',
          }))
        : reviewFile(source.file, controller.signal).then((r) => ({
            result: {
              issues: r.issues,
              rawCounts: r.rawCounts,
              ruleCount: r.ruleCount,
              durationMs: r.durationMs,
            } satisfies ReviewResult,
            text: r.text,
            report: r.report,
            reportName: r.filename,
          }));

    task
      .then(({ result, text, report: md, reportName: name }) => {
        if (controller.signal.aborted) return;
        setContent(text);
        setDraft(buildDraft(text, result.issues));
        setReport(md);
        setReportName(name);
        setPhase({ kind: 'ready', result });
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setPhase({
          kind: 'error',
          message: err instanceof Error ? err.message : '未知错误',
        });
      });

    return () => controller.abort();
  }, [source, nonce]);

  // loading 在事件处理器里同步设置（effect 内同步 setState 会触发级联渲染）
  const submit = useCallback((text: string) => {
    setPhase({ kind: 'loading' });
    setContent(text);
    setDisplayName('自定义稿件');
    setReport(null);
    setSource({ kind: 'text', text });
  }, []);

  const submitFile = useCallback((file: File) => {
    setPhase({ kind: 'loading' });
    setDisplayName(file.name);
    setReport(null);
    setSource({ kind: 'file', file });
  }, []);

  const retry = useCallback(() => {
    setPhase({ kind: 'loading' });
    setReport(null);
    setNonce((n) => n + 1);
  }, []);

  return {
    phase,
    sourceKind: source.kind,
    content,
    displayName,
    draft,
    report,
    reportName,
    submit,
    submitFile,
    retry,
  };
}
