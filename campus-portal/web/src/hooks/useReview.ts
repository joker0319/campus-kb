import { useCallback, useMemo, useReducer } from 'react';
import type { Issue, IssueFilter } from '../types';
import { countIssues, filterIssues, nextKey } from '../lib/review';

interface State {
  readonly selectedKey: string | null;
  readonly filter: IssueFilter;
  readonly dismissed: ReadonlySet<string>;
  readonly showMarks: boolean;
  /** 每次主动定位自增，文档区据此滚动 + 闪烁，避免用 key 变化误触发 */
  readonly scrollToken: number;
}

type Action =
  | { type: 'select'; key: string | null; scroll?: boolean }
  | { type: 'toggle'; key: string }
  | { type: 'filter'; filter: IssueFilter }
  | { type: 'marks'; on: boolean }
  | { type: 'reset' }
  | { type: 'step'; dir: 1 | -1; list: readonly Issue[] };

const initial: State = {
  selectedKey: 'NAME-001@3',
  filter: 'all',
  dismissed: new Set<string>(),
  showMarks: true,
  scrollToken: 0,
};

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'select':
      return {
        ...state,
        selectedKey: action.key,
        scrollToken: action.scroll ? state.scrollToken + 1 : state.scrollToken,
      };
    case 'toggle': {
      const next = new Set(state.dismissed);
      if (next.has(action.key)) next.delete(action.key);
      else next.add(action.key);
      const removed = next.has(action.key);
      return {
        ...state,
        dismissed: next,
        // 被忽略的条目会从当前筛选里消失，保持选中会指向一个看不见的项
        selectedKey: removed && state.selectedKey === action.key ? null : state.selectedKey,
      };
    }
    case 'filter':
      return { ...state, filter: action.filter };
    case 'marks':
      return { ...state, showMarks: action.on };
    case 'reset':
      return { ...state, dismissed: new Set<string>(), filter: 'all', selectedKey: null };
    case 'step': {
      const key = nextKey(action.list, state.selectedKey, action.dir);
      if (key === state.selectedKey) return state;
      return { ...state, selectedKey: key, scrollToken: state.scrollToken + 1 };
    }
    default:
      return state;
  }
}

export function useReview(issues: readonly Issue[]) {
  const [state, dispatch] = useReducer(reducer, initial);

  const counts = useMemo(() => countIssues(issues, state.dismissed), [issues, state.dismissed]);
  const visible = useMemo(
    () => filterIssues(issues, state.filter, state.dismissed),
    [issues, state.filter, state.dismissed],
  );
  const selected = useMemo(
    () => issues.find((it) => it.key === state.selectedKey) ?? null,
    [issues, state.selectedKey],
  );

  const select = useCallback((key: string | null, scroll = false) => {
    dispatch({ type: 'select', key, scroll });
  }, []);

  const step = useCallback(
    (dir: 1 | -1) => dispatch({ type: 'step', dir, list: visible }),
    [visible],
  );

  return { state, counts, visible, selected, dispatch, select, step };
}
