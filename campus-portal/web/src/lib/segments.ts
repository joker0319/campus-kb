export interface Seg {
  t: string;
  hit: boolean;
}

/**
 * 按命中词把文本切成片段，命中段标 hit。
 *
 * 用 split + 捕获组，而不是逐个 replace：
 * replace 会改写字符串位置，多处命中时后一个词的位置会漂移，
 * 重叠命中（如「城大」与「港城大」）还会互相吃掉。
 * split 保证片段顺序与原文逐字一致，渲染后不会丢字或改字。
 */
export function segments(text: string, hits: readonly string[]): Seg[] {
  const words = hits.filter(Boolean).map((h) => h.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  if (words.length === 0) return text ? [{ t: text, hit: false }] : [];
  const re = new RegExp(`(${words.join('|')})`, 'g');
  return text
    .split(re)
    .filter((t) => t !== '')
    .map((t) => ({ t, hit: hits.includes(t) }));
}
