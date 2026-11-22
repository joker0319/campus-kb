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
  hit: string;
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
    hit: f.hit || '',
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

/** 后端 POST /api/review-file 的响应（见 campus-kb/api/schemas.py） */
interface ApiReviewFileResponse {
  filename: string;
  text: string;
  findings: ApiFinding[];
  counts: ApiReviewResponse['counts'];
  ruleCount: number;
  report: string;
}

export interface ReviewFileResult {
  filename: string;
  /** 从 docx 提取出的正文，行号与后端命中保持一致 */
  text: string;
  issues: readonly Issue[];
  rawCounts: ApiReviewResponse['counts'];
  ruleCount: number;
  /** 后端生成的 Markdown 报告，供前端下载 */
  report: string;
  durationMs: number;
}

/** 上传 docx：后端提取正文 + 校验 + 生成 Markdown 报告。失败时抛错，不用假数据兜底。 */
export async function reviewFile(file: File, signal?: AbortSignal): Promise<ReviewFileResult> {
  const started = performance.now();
  const form = new FormData();
  form.append('file', file);
  const r = await fetch('/api/review-file', { method: 'POST', body: form, signal });
  if (!r.ok) throw new Error(`文件校验接口返回 ${r.status}`);
  const data = (await r.json()) as ApiReviewFileResponse;
  return {
    filename: data.filename,
    text: data.text,
    issues: data.findings.map(toIssue),
    rawCounts: data.counts,
    ruleCount: data.ruleCount,
    report: data.report,
    durationMs: Math.round(performance.now() - started),
  };
}

/** POST /api/chat 的请求与响应（见 campus-kb/api/schemas.py） */
export interface ChatTurn {
  readonly role: 'user' | 'assistant';
  readonly content: string;
}

export interface ChatSource {
  readonly ref: string;
  readonly kind: string;
  readonly title: string;
  readonly detail: string;
}

export interface ChatResult {
  readonly answer: string;
  readonly sources: readonly ChatSource[];
  readonly model: string;
}

/** AI 问答：把最近若干轮对话带上，后端检索知识库后交给 DeepSeek。 */
export async function postChat(
  message: string,
  history: readonly ChatTurn[] = [],
  signal?: AbortSignal,
): Promise<ChatResult> {
  const r = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, history }),
    signal,
  });
  if (!r.ok) {
    const detail = (await r.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(detail?.detail || `AI 问答接口返回 ${r.status}`);
  }
  return (await r.json()) as ChatResult;
}

/** POST /api/agent 的工具轨迹与结果（见 campus-kb/api/schemas.py） */
export interface AgentStep {
  readonly tool: string;
  readonly args: Record<string, string>;
  readonly result: {
    readonly kind: string;
    readonly items?: readonly Record<string, unknown>[];
    readonly total?: number;
    readonly counts?: { total: number; error: number; warn: number; info: number };
    readonly keyword?: string;
    readonly query?: string;
  };
  readonly callId: string;
}

export interface AgentResult {
  readonly answer: string;
  readonly steps: readonly AgentStep[];
  readonly model: string;
  readonly usedTools: readonly string[];
  readonly truncated: boolean;
}

/** Agent 对话：模型自选工具，工具在后端确定性执行；失败时透传后端 detail。 */
export async function postAgent(
  message: string,
  history: readonly ChatTurn[] = [],
  signal?: AbortSignal,
): Promise<AgentResult> {
  const r = await fetch('/api/agent', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, history }),
    signal,
  });
  if (!r.ok) {
    const detail = (await r.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(detail?.detail || `Agent 接口返回 ${r.status}`);
  }
  return (await r.json()) as AgentResult;
}

/** GET /api/rules 的一条规则（见 campus-kb/api/main.py list_rules） */
export interface ApiRule {
  id: string;
  category: string;
  severity: string;
  type: string;
  desc: string;
  suggestion: string;
  source: string;
  file: string;
}

export interface RulesResult {
  total: number;
  rules: readonly ApiRule[];
}

/** 取全部规则，供助手「问规范」按关键词在前端确定性筛选。 */
export async function getRules(signal?: AbortSignal): Promise<RulesResult> {
  const r = await fetch('/api/rules', { signal });
  if (!r.ok) throw new Error(`规则接口返回 ${r.status}`);
  const data = (await r.json()) as { total: number; rules: ApiRule[] };
  return { total: data.total, rules: data.rules };
}

/** GET /api/search 的一条命中（见 campus-kb/api/search.py） */
export interface ApiArchiveHit {
  file: string;
  line: number;
  excerpt: string;
  hits: number;
}

export interface ArchiveResult {
  query: string;
  total: number;
  scanned: number;
  results: readonly ApiArchiveHit[];
}

/** 语料库全文检索：多关键词空格分隔 AND。 */
export async function searchArchive(
  query: string,
  limit = 20,
  signal?: AbortSignal,
): Promise<ArchiveResult> {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  const r = await fetch(`/api/search?${params.toString()}`, { signal });
  if (!r.ok) throw new Error(`检索接口返回 ${r.status}`);
  return (await r.json()) as ArchiveResult;
}
