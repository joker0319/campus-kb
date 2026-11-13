import type { Counts, Issue, IssueFilter, Severity } from '../types';

/** 问题清单的筛选。已忽略的条目只在「已忽略」分组里出现，避免它们混进「全部」影响判断。 */
export function filterIssues(
  issues: readonly Issue[],
  filter: IssueFilter,
  dismissed: ReadonlySet<string>,
): Issue[] {
  return issues.filter((it) => {
    if (filter === 'dismissed') return dismissed.has(it.key);
    if (dismissed.has(it.key)) return false;
    if (filter === 'error') return it.severity === 'error';
    if (filter === 'warning') return it.severity === 'warning';
    return true;
  });
}

export function countIssues(issues: readonly Issue[], dismissed: ReadonlySet<string>): Counts {
  let error = 0;
  let warning = 0;
  let done = 0;
  for (const it of issues) {
    if (dismissed.has(it.key)) {
      done += 1;
      continue;
    }
    if (it.severity === 'error') error += 1;
    else warning += 1;
  }
  return { total: issues.length, error, warning, dismissed: done, open: error + warning };
}

export function buildIssueMap(issues: readonly Issue[]): ReadonlyMap<string, Issue> {
  return new Map(issues.map((it) => [it.key, it]));
}

/**
 * 一段文字可能同时踩到多条规则（例如标题同时违了 SUB-001 / SUB-002 / SUB-003）。
 * 只要其中有一条是错误，整段按错误样式标记——警告会淹没在错误里，弱化反而是误导。
 */
export function severityOfKeys(
  keys: readonly string[],
  map: ReadonlyMap<string, Issue>,
): Severity | null {
  let found: Severity | null = null;
  for (const k of keys) {
    const it = map.get(k);
    if (!it) continue;
    if (it.severity === 'error') return 'error';
    found = 'warning';
  }
  return found;
}

/** j/k 导航：越界时钳住而不是循环，避免从最后一条按 j 又跳回第一条的困惑。 */
export function nextKey(
  list: readonly Issue[],
  current: string | null,
  dir: 1 | -1,
): string | null {
  if (list.length === 0) return null;
  const idx = current ? list.findIndex((it) => it.key === current) : -1;
  if (idx < 0) return list[dir > 0 ? 0 : list.length - 1]?.key ?? null;
  const next = Math.min(Math.max(idx + dir, 0), list.length - 1);
  return list[next]?.key ?? null;
}

/** 只保留真实存在的问题 key，防止数据不同步时渲染出空标记 */
export function validKeys(
  keys: readonly string[] | undefined,
  map: ReadonlyMap<string, Issue>,
): string[] {
  if (!keys) return [];
  return keys.filter((k) => map.has(k));
}
