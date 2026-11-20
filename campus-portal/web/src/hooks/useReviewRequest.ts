import { useCallback, useEffect, useState } from 'react';
import { DRAFT_TEXT } from '../data/content';
import { postReview, type ReviewResult } from '../lib/api';

export type ReviewPhase =
  | { kind: 'loading' }
  | { kind: 'ready'; result: ReviewResult }
  | { kind: 'error'; message: string };

/** 请求后端校验；retry 触发重新校验，卸载时取消在途请求。 */
export function useReviewRequest() {
  const [phase, setPhase] = useState<ReviewPhase>({ kind: 'loading' });
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    postReview(DRAFT_TEXT, 'submission', controller.signal)
      .then((result) => {
        if (!controller.signal.aborted) setPhase({ kind: 'ready', result });
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setPhase({
          kind: 'error',
          message: err instanceof Error ? err.message : '未知错误',
        });
      });
    return () => controller.abort();
  }, [nonce]);

  // loading 在事件处理器里同步设置（effect 内同步 setState 会触发级联渲染）
  const retry = useCallback(() => {
    setPhase({ kind: 'loading' });
    setNonce((n) => n + 1);
  }, []);
  return { phase, retry };
}
