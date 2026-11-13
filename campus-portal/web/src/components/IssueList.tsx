import type { Counts, Issue, IssueFilter } from '../types';
import s from '../styles/desk.module.css';

interface Props {
  issues: readonly Issue[];
  counts: Counts;
  filter: IssueFilter;
  selectedKey: string | null;
  onFilter: (f: IssueFilter) => void;
  onSelect: (key: string) => void;
  onDismiss: (key: string) => void;
}

export function IssueList({
  issues,
  counts,
  filter,
  selectedKey,
  onFilter,
  onSelect,
  onDismiss,
}: Props) {
  const chips: { key: IssueFilter; label: string; n: number; dot?: string }[] = [
    { key: 'all', label: '全部', n: counts.open },
    { key: 'error', label: '错误', n: counts.error, dot: 'err' },
    { key: 'warning', label: '警告', n: counts.warning, dot: 'warn' },
    { key: 'dismissed', label: '已忽略', n: counts.dismissed },
  ];

  return (
    <section className={`${s.issues} js-anim`} style={{ ['--d' as string]: '.12s' }}>
      <div className={s.paneHead}>
        <div className={s.paneTitle}>
          <h2>问题清单</h2>
          <em>
            {counts.open} 项待处理 / 共 {counts.total} 项
          </em>
        </div>
        <div className={s.filters} role="tablist" aria-label="按级别筛选">
          {chips.map((c) => (
            <button
              key={c.key}
              type="button"
              role="tab"
              aria-selected={filter === c.key}
              className={`${s.chip} ${filter === c.key ? s.chipOn : ''}`}
              onClick={() => onFilter(c.key)}
            >
              {c.dot ? (
                <i
                  className={`${s.dot} ${c.dot === 'err' ? s.dotErr : s.dotWarn}`}
                  aria-hidden="true"
                />
              ) : null}
              {c.label} <b>{c.n}</b>
            </button>
          ))}
        </div>
      </div>

      <div className={s.ilist} role="list">
        {issues.length === 0 ? (
          <div className={s.emptyList}>这一组没有条目</div>
        ) : (
          issues.map((it) => {
            const on = it.key === selectedKey;
            const cls = [s.issue, it.severity === 'warning' ? s.issueW : '', on ? s.issueOn : '']
              .filter(Boolean)
              .join(' ');
            return (
              <div key={it.key} className={cls} role="listitem">
                <button
                  type="button"
                  className={s.issueMain}
                  onClick={() => onSelect(it.key)}
                  aria-pressed={on}
                >
                  <span className={s.iTop}>
                    <span className={`${s.lv} ${it.severity === 'error' ? s.lvE : s.lvW}`}>
                      {it.severity === 'error' ? '错误' : '警告'}
                    </span>
                    <span className={s.rule}>{it.ruleId}</span>
                    <span className={s.iLine}>第 {it.line} 行</span>
                  </span>
                  <span className={s.iMsg}>{it.message}</span>
                  <span className={s.iFix}>{it.fix}</span>
                </button>
                <button
                  type="button"
                  className={s.issueDismiss}
                  onClick={() => onDismiss(it.key)}
                  title={filter === 'dismissed' ? '恢复这条' : '忽略这条'}
                >
                  {filter === 'dismissed' ? '恢复' : '忽略'}
                </button>
              </div>
            );
          })
        )}
      </div>
    </section>
  );
}
