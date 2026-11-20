export type Severity = 'error' | 'warning';

export type RuleId =
  | 'SUB-001'
  | 'SUB-002'
  | 'SUB-003'
  | 'NAME-001'
  | 'NAME-002'
  | 'TITLE-001'
  | 'SOEV-002'
  | 'SOEV-004'
  | 'PUNCT-001'
  | 'PUNCT-002'
  | 'PUNCT-003'
  | 'ENG-001'
  | 'RANK-001';

/** 规则定义：出处与原文摘录，供「依据」栏使用 */
export interface Rule {
  readonly id: RuleId;
  readonly name: string;
  readonly source: string;
  readonly quote: string;
  /** 判定说明，支持 **加粗** 标记 */
  readonly note?: string;
}

/**
 * 一条命中。
 * key = `${ruleId}@${line}`：同一条规则可能在一篇稿子里命中多次（如 PUNCT-001），
 * 因此不能拿 ruleId 当 React key，也不能用数组下标（筛选后下标会漂移）。
 */
export interface Issue {
  readonly key: string;
  readonly ruleId: RuleId;
  readonly severity: Severity;
  readonly line: number;
  readonly message: string;
  readonly fix: string;
  /** 后端给出的精确命中子串，供任意稿件动态标红；行级规则为整行 */
  readonly hit: string;
}

/** 正文片段；带 issueKeys 的片段渲染为可点击的校样标记 */
export interface Segment {
  readonly text: string;
  readonly issueKeys?: readonly string[];
}

export interface Paragraph {
  readonly line: number;
  readonly isTitle?: boolean;
  readonly segments: readonly Segment[];
}

export type Draft = readonly Paragraph[];

export type IssueFilter = 'all' | 'error' | 'warning' | 'dismissed';

export interface Counts {
  readonly total: number;
  readonly error: number;
  readonly warning: number;
  readonly dismissed: number;
  readonly open: number;
}
