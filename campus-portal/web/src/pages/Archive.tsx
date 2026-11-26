import { useEffect, useState, type FormEvent } from 'react';
import {
  getArchive,
  getArchiveArticle,
  type WechatArticle,
  type WechatArchive,
  type WechatArticleDetail,
} from '../lib/api';
import { SoftBackdrop } from '../components/SoftBackdrop';
import s from '../styles/archive.module.css';

const monthLabel = (month: string) => {
  const [year, mm] = month.split('-');
  return `${year} 年 ${Number(mm)} 月`;
};

const dayLabel = (published: string) => {
  const [, mm, dd] = published.split('-');
  return `${Number(mm)}.${Number(dd)}`;
};

/** 往期公众号推文：按时间线倒序浏览，可搜、可看正文、可直达微信原文。 */
export default function Archive() {
  const [draft, setDraft] = useState('');
  const [query, setQuery] = useState('');
  const [month, setMonth] = useState('');
  const [data, setData] = useState<WechatArchive | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [active, setActive] = useState<WechatArticle | null>(null);
  const [detail, setDetail] = useState<WechatArticleDetail | null>(null);
  const [detailError, setDetailError] = useState('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getArchive(query, month)
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setError('');
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : '档案加载失败');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [query, month]);

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    setDetail(null);
    setDetailError('');
    getArchiveArticle(active.file)
      .then((result) => {
        if (!cancelled) setDetail(result);
      })
      .catch((err: unknown) => {
        if (!cancelled) setDetailError(err instanceof Error ? err.message : '正文加载失败');
      });
    return () => {
      cancelled = true;
    };
  }, [active]);

  useEffect(() => {
    if (!active) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setActive(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [active]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setQuery(draft.trim());
  };

  const clearFilters = () => {
    setDraft('');
    setQuery('');
    setMonth('');
  };

  // 下拉选项用全量月份（筛选后仍能切换）；时间线只渲染真正有文章的月份，
  // 否则选了某个月会出现其它月份「0 篇」的空分组。
  const groups = data?.months ?? [];
  const visibleGroups = groups.filter((g) =>
    data?.articles.some((article) => article.month === g.month),
  );
  // 下拉选项按年份分组，跨年时先选年份、再选月份。
  const yearGroups = groups.reduce<Record<string, { month: string; count: number }[]>>(
    (acc, item) => {
      const year = item.month.split('-')[0] ?? '';
      (acc[year] ??= []).push(item);
      return acc;
    },
    {},
  );

  return (
    <div className={s.page}>
      <SoftBackdrop />
      <header className={s.bar}>
        <a className={s.back} href="#/">
          ← 返回首页
        </a>
        <span className={s.barName}>往期推文</span>
        <span className={s.barTag}>
          {data ? `${data.total} 篇 · 公众号原文可回溯` : '公众号档案 · 按时间倒序'}
        </span>
      </header>

      <div className={s.body}>
        <div className={s.inner}>
          <section className={s.intro}>
            <p className={s.kicker}>CONTENT ARCHIVE</p>
            <h1 className={s.title}>往期公众号推文</h1>
            <p className={s.sub}>
              按发布时间倒序排列，每篇都给出原文链接与入库正文。
              <br />
              搜索标题或正文，快速找到可参考的往期选题。
            </p>
          </section>

          <div className={s.filters}>
            <form className={s.search} onSubmit={submit} role="search">
              <input
                className={s.input}
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                placeholder="搜索标题或正文，如「科研」「开学」"
                aria-label="搜索推文"
              />
              <button className={s.searchBtn} type="submit">
                搜索
              </button>
            </form>
            <div className={s.monthFilter}>
              <button
                type="button"
                className={`${s.allBtn} ${month === '' ? s.allBtnOn : ''}`}
                aria-pressed={month === ''}
                onClick={() => setMonth('')}
              >
                全部
              </button>
              <label className={s.monthLabel} htmlFor="archive-month">
                按月份查找
              </label>
              <select
                id="archive-month"
                className={s.select}
                value={month}
                onChange={(event) => setMonth(event.target.value)}
                aria-label="按月份查找"
              >
                <option value="">选择月份</option>
                {Object.entries(yearGroups).map(([year, items]) => (
                  <optgroup key={year} label={`${year} 年`}>
                    {items.map((item) => (
                      <option key={item.month} value={item.month}>
                        {Number(item.month.split('-')[1])} 月（{item.count} 篇）
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </div>
          </div>

          {error ? (
            <p className={s.empty} role="alert">
              加载失败：{error}
            </p>
          ) : loading ? (
            <p className={s.empty}>正在整理往期推文…</p>
          ) : !data || data.articles.length === 0 ? (
            <div className={s.empty}>
              <p>没有找到匹配的推文。</p>
              <button type="button" className={s.clear} onClick={clearFilters}>
                清除筛选
              </button>
            </div>
          ) : (
            <div className={s.timeline}>
              {visibleGroups.map((group) => (
                <section className={s.group} key={group.month}>
                  <div className={s.groupHead}>
                    <h2 className={s.groupTitle}>{monthLabel(group.month)}</h2>
                    <span className={s.groupCount}>
                      {data.articles.filter((a) => a.month === group.month).length} 篇
                    </span>
                  </div>
                  <div className={s.items}>
                    {data.articles
                      .filter((article) => article.month === group.month)
                      .map((article) => (
                        <article className={s.item} key={article.file}>
                          <div className={s.dot} aria-hidden="true" />
                          <div className={s.day}>{dayLabel(article.published)}</div>
                          <div className={s.card}>
                            <a
                              className={s.cardTitle}
                              href={article.url}
                              target="_blank"
                              rel="noopener noreferrer"
                            >
                              {article.title}
                            </a>
                            <p className={s.excerpt}>{article.excerpt}</p>
                            <div className={s.meta}>
                              <span>{article.chars.toLocaleString()} 字</span>
                              <span>{article.images} 张配图</span>
                              <button
                                type="button"
                                className={s.preview}
                                onClick={() => setActive(article)}
                              >
                                预览正文
                              </button>
                              <a
                                className={s.origin}
                                href={article.url}
                                target="_blank"
                                rel="noopener noreferrer"
                              >
                                看微信原文 ↗
                              </a>
                            </div>
                          </div>
                        </article>
                      ))}
                  </div>
                </section>
              ))}
            </div>
          )}
        </div>
      </div>

      {active ? (
        <div className={s.overlay} onClick={() => setActive(null)}>
          <div
            className={s.modal}
            role="dialog"
            aria-modal="true"
            aria-label={active.title}
            onClick={(event) => event.stopPropagation()}
          >
            <header className={s.modalHead}>
              <div>
                <h2 className={s.modalTitle}>{active.title}</h2>
                <p className={s.modalMeta}>
                  {active.published} · 入库正文
                  {detail?.truncated ? '（已截断，请以原文为准）' : ''}
                </p>
              </div>
              <button
                type="button"
                className={s.close}
                onClick={() => setActive(null)}
                aria-label="关闭预览"
              >
                ×
              </button>
            </header>
            <div className={s.modalBody}>
              {detailError ? (
                <p className={s.empty}>{detailError}</p>
              ) : !detail ? (
                <p className={s.empty}>正在读取入库正文…</p>
              ) : (
                <div className={s.text}>
                  {detail.text.split('\n').map((line, index) =>
                    line.trim() ? <p key={index}>{line.trim()}</p> : null,
                  )}
                </div>
              )}
            </div>
            <footer className={s.modalFoot}>
              <a
                className={s.originBtn}
                href={active.url}
                target="_blank"
                rel="noopener noreferrer"
              >
                打开公众号原文 ↗
              </a>
            </footer>
          </div>
        </div>
      ) : null}
    </div>
  );
}
