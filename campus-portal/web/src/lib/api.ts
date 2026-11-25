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

export interface AgentStreamHandlers {
  /** 首帧：本次使用的模型名 */
  onMeta?: (model: string) => void;
  /** 一次工具执行完成，index 为本轮轨迹序号（从 0 开始） */
  onStep?: (step: AgentStep, index: number) => void;
  /** 最终回答的文本增量 */
  onDelta?: (text: string) => void;
}

type AgentStreamEvent = {
  type?: string;
  model?: string;
  step?: AgentStep;
  text?: string;
  result?: AgentResult;
  message?: string;
};

/** 助手流式问答：工具轨迹与回答边到边显示，结束时返回完整结果（同 postAgent）。 */
export async function streamAgent(
  message: string,
  history: readonly ChatTurn[] = [],
  handlers: AgentStreamHandlers = {},
  signal?: AbortSignal,
): Promise<AgentResult> {
  const r = await fetch('/api/agent/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ message, history }),
    signal,
  });
  if (!r.ok) {
    const detail = (await r.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(detail?.detail || `助手流式接口返回 ${r.status}`);
  }
  if (!r.body) throw new Error('当前浏览器不支持流式读取');

  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  const box: { result: AgentResult | null } = { result: null };
  let stepIndex = 0;
  let buffer = '';

  const handle = (frame: string) => {
    const line = frame.split('\n').find((ln) => ln.startsWith('data:'));
    if (!line) return;
    let event: AgentStreamEvent;
    try {
      event = JSON.parse(line.slice(5).trim()) as AgentStreamEvent;
    } catch {
      return;
    }
    if (event.type === 'meta' && event.model) {
      handlers.onMeta?.(event.model);
    } else if (event.type === 'step' && event.step) {
      handlers.onStep?.(event.step, stepIndex++);
    } else if (event.type === 'delta' && event.text) {
      handlers.onDelta?.(event.text);
    } else if (event.type === 'done' && event.result) {
      box.result = event.result;
    } else if (event.type === 'error') {
      throw new Error(event.message || '助手调用失败，请重试');
    }
  };

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let cut = buffer.indexOf('\n\n');
      while (cut >= 0) {
        const frame = buffer.slice(0, cut);
        buffer = buffer.slice(cut + 2);
        handle(frame);
        cut = buffer.indexOf('\n\n');
      }
    }
  } finally {
    reader.releaseLock();
  }

  if (!box.result) throw new Error('回答中断，没有收到完整结果');
  return box.result;
}

/** POST /api/compose 文章生成（见 campus-kb/api/compose.py / schemas.py） */
export interface ComposeSource {
  readonly ref: string;
  readonly kind: string;
  readonly text: string;
  readonly file: string;
  readonly line: number;
}

export interface ComposeParagraph {
  readonly text: string;
  readonly cites: readonly string[];
}

export interface ComposeSection {
  readonly heading: string;
  readonly paragraphs: readonly ComposeParagraph[];
}

export interface ComposeArticle {
  readonly title: string;
  readonly lead: string;
  readonly sections: readonly ComposeSection[];
  readonly imageSuggestions: readonly { readonly after: string; readonly description: string }[];
}

/** 可选文体：auto 按选题判定，其余显式指定 */
export type ComposeStyleId = 'auto' | 'news' | 'celebration' | 'speech';

export interface ComposeStyle {
  readonly id: string;
  readonly name: string;
  readonly auto: boolean;
}

/** 往期推文里的真实配图（后端从图库挑的，不是模型编的配图建议） */
export interface ComposeFigure {
  readonly id: string;
  readonly url: string;
  readonly caption: string;
  /** scene 实景 / crowd 合影 / chart 图表截图 / poster 海报长图 */
  readonly kind: string;
  readonly width: number;
  readonly height: number;
  readonly sourceTitle: string;
  readonly sourcePublished: string;
  readonly sectionIndex: number;
  readonly sectionHeading: string;
  readonly score: number;
  /** true 表示只跟来源文章相关、图注对不上，需人工确认 */
  readonly weak: boolean;
}

export interface ComposeResult {
  readonly topic: string;
  readonly article: ComposeArticle;
  readonly markdown: string;
  /** 内联样式的 HTML 片段，粘进公众号编辑器即带版式 */
  readonly html: string;
  readonly sources: readonly ComposeSource[];
  readonly rules: readonly Record<string, unknown>[];
  readonly meta: { readonly terms: readonly string[]; readonly scanned: number };
  readonly citations: {
    readonly cited: readonly ComposeSource[];
    readonly uncitedParagraphs: number;
    readonly invalidCites: readonly string[];
    readonly paragraphCount: number;
    readonly grounded: boolean;
  };
  readonly review: {
    readonly counts: {
      readonly total: number;
      readonly error: number;
      readonly warn: number;
      readonly info: number;
    };
    readonly findings: readonly {
      readonly ruleId: string;
      readonly line: number;
      readonly severity: string;
      readonly message: string;
      readonly suggestion: string;
    }[];
  };
  readonly style: ComposeStyle;
  readonly figures?: readonly ComposeFigure[];
  readonly model: string;
}

/** 文章生成：选题 + 文体 → 检索知识库成稿 → 出处与规范校验；失败时透传后端 detail。 */
export async function postCompose(
  topic: string,
  style: ComposeStyleId = 'auto',
  signal?: AbortSignal,
): Promise<ComposeResult> {
  const r = await fetch('/api/compose', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ topic, style }),
    signal,
  });
  if (!r.ok) {
    const detail = (await r.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(detail?.detail || `文章生成接口返回 ${r.status}`);
  }
  return (await r.json()) as ComposeResult;
}

export interface StreamHandlers {
  /** 每次收到模型原文增量 */
  onDelta?: (text: string) => void;
  /** 后端定下的文体（首帧就给，用来提前显示"自动判断为…"） */
  onMeta?: (style: ComposeStyle) => void;
}

type StreamEvent = {
  type?: string;
  text?: string;
  style?: ComposeStyle;
  result?: ComposeResult;
  message?: string;
};

/**
 * 流式成稿：以 SSE 边收边回调，结束时返回完整结果（结构同 postCompose）。
 * 首帧前的静默是后端在检索素材，不是卡住。
 */
export async function streamCompose(
  topic: string,
  style: ComposeStyleId = 'auto',
  handlers: StreamHandlers = {},
  signal?: AbortSignal,
): Promise<ComposeResult> {
  const r = await fetch('/api/compose/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ topic, style }),
    signal,
  });
  if (!r.ok) {
    const detail = (await r.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(detail?.detail || `文章生成接口返回 ${r.status}`);
  }
  if (!r.body) throw new Error('当前浏览器不支持流式读取');

  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  // 闭包里赋值不会被 TS 的控制流分析看见，所以装在对象里
  const box: { result: ComposeResult | null } = { result: null };
  let buffer = '';

  const handle = (frame: string) => {
    const line = frame.split('\n').find((ln) => ln.startsWith('data:'));
    if (!line) return;
    let event: StreamEvent;
    try {
      event = JSON.parse(line.slice(5).trim()) as StreamEvent;
    } catch {
      return;
    }
    if (event.type === 'delta' && event.text) {
      handlers.onDelta?.(event.text);
    } else if (event.type === 'meta' && event.style) {
      handlers.onMeta?.(event.style);
    } else if (event.type === 'done' && event.result) {
      box.result = event.result;
    } else if (event.type === 'error') {
      throw new Error(event.message || '生成失败，请重试');
    }
  };

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let cut = buffer.indexOf('\n\n');
      while (cut >= 0) {
        const frame = buffer.slice(0, cut);
        buffer = buffer.slice(cut + 2);
        handle(frame);
        cut = buffer.indexOf('\n\n');
      }
    }
  } finally {
    reader.releaseLock();
  }

  if (!box.result) throw new Error('生成中断，没有收到完整稿件');
  return box.result;
}

export interface RevisePayload {
  readonly topic: string;
  readonly instruction: string;
  readonly article: ComposeArticle;
  readonly sources: readonly ComposeSource[];
  readonly rules: readonly Record<string, unknown>[];
  /** 沿用成稿时的文体，避免改稿把致辞写成新闻腔 */
  readonly style: string;
}

/**
 * 改稿：把上一版草稿连同素材编号一起回传，后端按指令继续改。
 * sources 必须原样带回，否则正文里的 [A#] 会失去指向。
 */
export async function postRevise(
  payload: RevisePayload,
  signal?: AbortSignal,
): Promise<ComposeResult> {
  const r = await fetch('/api/compose/revise', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  });
  if (!r.ok) {
    const detail = (await r.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(detail?.detail || `改稿接口返回 ${r.status}`);
  }
  return (await r.json()) as ComposeResult;
}

/** GET /api/rules 的一条规则（见 campus-kb/api/main.py list_rules） */ export interface ApiRule {
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
