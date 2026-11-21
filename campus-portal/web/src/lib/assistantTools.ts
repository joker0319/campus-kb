/**
 * 助手的确定性工具层。
 *
 * 不接大模型：三个能力各自对应一个后端接口，本模块只把接口响应整理成
 * 「逐条带出处」的回答块。查不到就明确说查不到，不臆测、不补造结论。
 * 纯函数，便于测试。
 */

import type { ArchiveResult, ReviewResult, RulesResult } from './api';

export type ToolKind = 'rules' | 'search' | 'review';

export const TOOLS: readonly { kind: ToolKind; name: string; desc: string }[] = [
  { kind: 'rules', name: '问规范', desc: '按关键词查规则，逐条给依据。' },
  { kind: 'search', name: '查档案', desc: '在入库档案里全文检索，返回文件与行号。' },
  { kind: 'review', name: '校稿件', desc: '粘一段正文，命中处给改法。' },
] as const;

/** 一条回答项：标题 + 出处/定位 + 说明 */
export interface AnswerItem {
  readonly title: string;
  readonly meta: string;
  readonly detail: string;
}

/** 一次工具调用的结构化回答 */
export interface Answer {
  readonly tool: ToolKind;
  readonly summary: string;
  readonly items: readonly AnswerItem[];
}

const severityLabel = (s: string): string =>
  s === 'error' ? '错误' : s === 'warn' ? '警告' : '提示';

/** 问规范：在本地已取回的规则集里按关键词确定性筛选（不调用 LLM）。 */
export function answerFromRules(query: string, result: RulesResult): Answer {
  const q = query.trim().toLowerCase();
  if (!q) {
    return { tool: 'rules', summary: '请输入关键词，例如「标点」「序数」「校名」。', items: [] };
  }
  const matched = result.rules.filter((r) =>
    [r.id, r.category, r.desc, r.suggestion, r.source, r.type].join(' ').toLowerCase().includes(q),
  );
  if (matched.length === 0) {
    return {
      tool: 'rules',
      summary: `未找到与「${query.trim()}」相关的规范，不做臆测。`,
      items: [],
    };
  }
  return {
    tool: 'rules',
    summary: `命中 ${matched.length} 条规范（共 ${result.total} 条）：`,
    items: matched.map((r) => ({
      title: `[${r.id}] ${r.desc}`,
      meta: `出处：${r.source || r.file}`,
      detail: r.suggestion ? `建议：${r.suggestion}` : '以规范原文为准',
    })),
  };
}

/** 查档案：把全文检索结果逐条列出，带文件名与行号。 */
export function answerFromArchive(query: string, result: ArchiveResult): Answer {
  const q = query.trim();
  if (!q) {
    return { tool: 'search', summary: '请输入检索词，多个词用空格分隔。', items: [] };
  }
  if (result.results.length === 0) {
    return {
      tool: 'search',
      summary: `在 ${result.scanned} 份入库档案中未找到「${q}」，不做臆测。`,
      items: [],
    };
  }
  return {
    tool: 'search',
    summary: `在 ${result.scanned} 份档案中命中 ${result.total} 处，列出前 ${result.results.length} 条：`,
    items: result.results.map((h) => ({
      title: h.excerpt,
      meta: `${h.file}${h.line > 0 ? ` · 第 ${h.line} 行` : ''} · 命中 ${h.hits} 次`,
      detail: '',
    })),
  };
}

/** 校稿件：把校验命中逐条列出，带规则号、行号与改法。 */
export function answerFromReview(result: ReviewResult): Answer {
  if (result.issues.length === 0) {
    return {
      tool: 'review',
      summary: `已按 ${result.ruleCount} 条规则校验，未发现问题。`,
      items: [],
    };
  }
  return {
    tool: 'review',
    summary: `按 ${result.ruleCount} 条规则校验，发现 ${result.issues.length} 处问题（错误 ${result.rawCounts.error} / 警告 ${result.rawCounts.warn}）：`,
    items: result.issues.map((i) => ({
      title: i.message,
      meta: `[${i.ruleId}] · ${severityLabel(i.severity)} · 第 ${i.line} 行`,
      detail: `改法：${i.fix}`,
    })),
  };
}
