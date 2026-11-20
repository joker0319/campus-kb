import type { Issue, RuleId, Severity } from '../types';

/** 后端 POST /api/review 的响应（见 campus-kb/api/schemas.py） */
interface ApiFinding {
  key: string;
  ruleId: string;
  severity: string;
  line: number;
  message: string;
  excerpt: string;
  suggestion: string;
}

interface ApiReviewResponse {
  findings: ApiFinding[];
  counts: { total: number; error: number; warn: number; info: number };
  ruleCount: number;
}

export interface ReviewResult {
  issues: readonly Issue[];
  rawCounts: ApiReviewResponse['counts'];
  ruleCount: number;
  durationMs: number;
}

/** 引擎三档严重度 → 前端两档；counts 保留原始分档，只有 Issue 需要收敛 */
export function toSeverity(s: string): Severity {
  return s === 'error' ? 'error' : 'warning';
}

/** 把后端 finding 映射为前端 Issue；key 由后端生成，前端不重算（避免去重规则打架） */
export function toIssue(f: ApiFinding): Issue {
  return {
    key: f.key,
    ruleId: f.ruleId as RuleId,
    severity: toSeverity(f.severity),
    line: f.line,
    message: f.message,
    fix: f.suggestion || '以规范原文为准',
  };
}

/** 调真实校验接口。失败时抛错，由 hook 呈现错误态，不使用假数据兜底。 */
export async function postReview(
  content: string,
  mode: 'submission' | 'archive' = 'submission',
  signal?: AbortSignal,
): Promise<ReviewResult> {
  const started = performance.now();
  const r = await fetch('/api/review', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, mode }),
    signal,
  });
  if (!r.ok) throw new Error(`校验接口返回 ${r.status}`);
  const data = (await r.json()) as ApiReviewResponse;
  return {
    issues: data.findings.map(toIssue),
    rawCounts: data.counts,
    ruleCount: data.ruleCount,
    durationMs: Math.round(performance.now() - started),
  };
}
