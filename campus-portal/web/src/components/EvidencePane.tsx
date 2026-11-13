import { Fragment } from 'react';
import type { Issue, Rule } from '../types';
import s from '../styles/desk.module.css';
import { IconFile } from './icons';

interface Props {
  issue: Issue | null;
  rule: Rule | null;
  /** 嵌在底部抽屉里时由抽屉提供标题，避免两级抬头重复 */
  headless?: boolean;
}

/** 只支持 **加粗**，不引入 markdown 解析器——依据栏的富文本需求就这一种 */
function Rich({ text }: { text: string }) {
  const parts = text.split('**');
  return (
    <>
      {parts.map((p, i) =>
        i % 2 === 1 ? <strong key={i}>{p}</strong> : <Fragment key={i}>{p}</Fragment>,
      )}
    </>
  );
}

export function EvidencePane({ issue, rule, headless = false }: Props) {
  if (!issue || !rule) {
    return (
      <aside
        className={`${s.source} js-anim`}
        style={{ ['--d' as string]: '.16s' }}
        aria-label="判定依据"
      >
        {headless ? null : (
          <div className={s.srcHead}>
            <div className={s.srcKey}>判定依据</div>
          </div>
        )}
        <div className={s.emptyList}>
          在问题清单中选一条
          <br />
          这里会显示它出自哪份规范、哪一章
        </div>
      </aside>
    );
  }

  return (
    <aside
      className={`${s.source} js-anim`}
      style={{ ['--d' as string]: '.16s' }}
      aria-label="判定依据"
    >
      {headless ? null : (
        <div className={s.srcHead}>
          <div className={s.srcKey}>判定依据</div>
          <div className={s.srcRule}>
            <span>{rule.id}</span>
            <span className={s.srcName}>{rule.name}</span>
          </div>
        </div>
      )}
      <div className={s.srcBody}>
        <div className={s.srcSec}>
          <div className={s.srcLabel}>判定</div>
          <div className={s.judge}>{issue.message}</div>
        </div>

        <div className={s.srcSec}>
          <div className={s.srcLabel}>原文摘录</div>
          <div className={s.quote}>{rule.quote}</div>
        </div>

        <div className={s.srcSec}>
          <div className={s.srcLabel}>出处</div>
          <div className={s.cite}>
            <IconFile />
            <span>{rule.source}</span>
          </div>
        </div>

        {rule.note ? (
          <div className={s.srcSec}>
            <div className={s.note}>
              <Rich text={rule.note} />
            </div>
          </div>
        ) : null}
      </div>
    </aside>
  );
}
