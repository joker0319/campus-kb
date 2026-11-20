import { describe, expect, it } from 'vitest';
import type { Issue } from '../types';
import {
  buildIssueMap,
  countIssues,
  filterIssues,
  nextKey,
  severityOfKeys,
  validKeys,
} from './review';

const mk = (key: string, severity: 'error' | 'warning'): Issue => ({
  key,
  ruleId: 'PUNCT-001',
  severity,
  line: 1,
  message: key,
  fix: '',
  hit: '',
});

const A = mk('A', 'error');
const B = mk('B', 'warning');
const C = mk('C', 'warning');
const D = mk('D', 'error');
const ALL = [A, B, C, D];

describe('filterIssues', () => {
  it('全部：剔除已忽略', () => {
    expect(filterIssues(ALL, 'all', new Set(['B'])).map((i) => i.key)).toEqual(['A', 'C', 'D']);
  });

  it('错误 / 警告分组各自独立', () => {
    expect(filterIssues(ALL, 'error', new Set()).map((i) => i.key)).toEqual(['A', 'D']);
    expect(filterIssues(ALL, 'warning', new Set()).map((i) => i.key)).toEqual(['B', 'C']);
  });

  it('已忽略分组只显示被忽略的，且不受筛选影响', () => {
    expect(filterIssues(ALL, 'dismissed', new Set(['B', 'D'])).map((i) => i.key)).toEqual([
      'B',
      'D',
    ]);
    expect(filterIssues(ALL, 'dismissed', new Set())).toEqual([]);
  });
});

describe('countIssues', () => {
  it('忽略一条警告后计数同步', () => {
    expect(countIssues(ALL, new Set())).toEqual({
      total: 4,
      error: 2,
      warning: 2,
      dismissed: 0,
      open: 4,
    });
    expect(countIssues(ALL, new Set(['C']))).toEqual({
      total: 4,
      error: 2,
      warning: 1,
      dismissed: 1,
      open: 3,
    });
  });
});

describe('nextKey', () => {
  it('未选中时从两端进入', () => {
    expect(nextKey(ALL, null, 1)).toBe('A');
    expect(nextKey(ALL, null, -1)).toBe('D');
  });

  it('钳住边界，不循环', () => {
    expect(nextKey(ALL, 'D', 1)).toBe('D');
    expect(nextKey(ALL, 'A', -1)).toBe('A');
  });

  it('空清单返回 null', () => {
    expect(nextKey([], 'A', 1)).toBeNull();
  });

  it('当前项已被筛掉时回落到首项', () => {
    expect(nextKey([A, B], 'D', 1)).toBe('A');
  });
});

describe('severityOfKeys', () => {
  const map = buildIssueMap(ALL);

  it('任一条为错误即整段标红', () => {
    expect(severityOfKeys(['B', 'A'], map)).toBe('error');
  });

  it('只有警告时为警告', () => {
    expect(severityOfKeys(['B', 'C'], map)).toBe('warning');
  });

  it('全部失效 key 返回 null', () => {
    expect(severityOfKeys(['X'], map)).toBeNull();
  });
});

describe('validKeys', () => {
  const map = buildIssueMap(ALL);

  it('过滤掉不存在的 key', () => {
    expect(validKeys(['A', 'X'], map)).toEqual(['A']);
    expect(validKeys(undefined, map)).toEqual([]);
  });
});
