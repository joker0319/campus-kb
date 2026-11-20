import { useCallback, useEffect, useState } from 'react';
import { DRAFT, DRAFT_TEXT } from '../data/content';
import { buildDraft } from '../lib/buildDraft';
import { postReview, type ReviewResult } from '../lib/api';
import type { Draft } from '../types';

export type ReviewPhase =
  | { kind: 'loading' }
  | { kind: 'ready'; result: ReviewResult }
  | { kind: 'error'; message: string };

/** 当前送审内容与校验结果；submit 可换成任意粘贴的正文。 */
export function useReviewRequest() {
  const [phase, setPhase] = useState<ReviewPhase>({ kind: 'loading' });
  const [content, setContent] = useState(DRAFT_TEXT);
  const [draft, setDraft] = useState<Draft>(DRAFT);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    postReview(content, 'submission', controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return;
        setDraft(buildDraft(content, result.issues));
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
  }, [content, nonce]);

  // loading 在事件处理器里同步设置（effect 内同步 setState 会触发级联渲染）
  const submit = useCallback((text: string) => {
    setPhase({ kind: 'loading' });
    setContent(text);
  }, []);

  const retry = useCallback(() => {
    setPhase({ kind: 'loading' });
    setNonce((n) => n + 1);
  }, []);

  return { phase, content, draft, submit, retry };
}
