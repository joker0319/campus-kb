import type { Draft, Issue, Paragraph, Segment } from '../types';
import { segments } from './segments';

/**
 * 从任意正文 + 真实命中构建带 issueKeys 的稿件片段。
 *
 * 行号严格沿用后端 findings.line（原文 1-based 换行计数），空行不渲染但行号不重排；
 * 用后端返回的精确 hit 切分文本，因此不需要为每篇新稿件手工标注片段。
 */
export function buildDraft(text: string, issues: readonly Issue[]): Draft {
  const lines = text.split('\n');
  const byLine = new Map<number, Issue[]>();
  for (const it of issues) {
    const arr = byLine.get(it.line) ?? [];
    arr.push(it);
    byLine.set(it.line, arr);
  }

  const paras: Paragraph[] = [];
  let first = true;
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i] ?? '';
    const lineNo = i + 1;
    if (!line.trim()) continue;

    const lineIssues = byLine.get(lineNo) ?? [];
    // 同一命中文本可能被多条规则命中（如标题违反 SUB-001/002/003），合并 key
    const hitKeys = new Map<string, string[]>();
    for (const it of lineIssues) {
      if (!it.hit || !line.includes(it.hit)) continue;
      const keys = hitKeys.get(it.hit) ?? [];
      keys.push(it.key);
      hitKeys.set(it.hit, keys);
    }

    // 长 hit 优先，避免短 hit（如「台」）把长 hit（如「中、港、台」）切断
    const words = [...hitKeys.keys()].sort((a, b) => b.length - a.length);
    const outSegs: Segment[] = segments(line, words).map((sg) => ({
      text: sg.t,
      issueKeys: sg.hit ? hitKeys.get(sg.t) : undefined,
    }));

    // 行级规则或 hit 不在该行时，挂到本行第一个非空片段，保证每条命中都能点回正文
    const attached = new Set(outSegs.flatMap((sg) => sg.issueKeys ?? []));
    const missing = lineIssues.filter((it) => !attached.has(it.key));
    if (missing.length > 0) {
      const idx = outSegs.findIndex((sg) => sg.text.trim());
      if (idx >= 0) {
        const seg = outSegs[idx]!;
        outSegs[idx] = {
          ...seg,
          issueKeys: [...(seg.issueKeys ?? []), ...missing.map((it) => it.key)],
        };
      }
    }

    paras.push({
      line: lineNo,
      ...(first ? { isTitle: true } : {}),
      segments: outSegs,
    });
    first = false;
  }
  return paras;
}
