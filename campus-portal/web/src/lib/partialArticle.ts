/** 流式成稿时，把还没写完的 JSON 片段解析成能渲染的草稿。 */

export interface PartialSection {
  heading: string;
  paragraphs: string[];
}

export interface PartialArticle {
  title: string;
  lead: string;
  sections: PartialSection[];
  /** 已接收的原始字符数，用来给"正在写"一点进度感 */
  chars: number;
}

/**
 * 只认**已经闭合**的字符串字段，所以半句话不会被吐出来再改。
 * 模型按 title → lead → sections 的顺序输出，于是能边收边把段落铺开。
 */
const FIELD_RE = /(?<!\\)"(title|lead|heading|text)"\s*:\s*"((?:[^"\\]|\\.)*)"/g;

function unescapeJson(inner: string): string {
  try {
    return JSON.parse(`"${inner}"`) as string;
  } catch {
    // 极端情况下转义序列本身不合法：退回原文，不要让预览整段消失
    return inner;
  }
}

export function readPartial(raw: string): PartialArticle {
  const out: PartialArticle = { title: '', lead: '', sections: [], chars: raw.length };
  let current: PartialSection | null = null;

  // 每次新建正则：复用会带 lastIndex 状态
  for (const match of raw.matchAll(FIELD_RE)) {
    const key = match[1] ?? '';
    const value = unescapeJson(match[2] ?? '');
    if (!value) continue;

    if (key === 'title') {
      out.title = value;
      continue;
    }
    if (key === 'lead') {
      out.lead = value;
      continue;
    }
    if (key === 'heading') {
      current = { heading: value, paragraphs: [] };
      out.sections.push(current);
      continue;
    }
    if (key === 'text') {
      if (!current) {
        // 模型偶尔省略 heading：仍然要显示正文，挂到一个空标题节下
        current = { heading: '', paragraphs: [] };
        out.sections.push(current);
      }
      current.paragraphs.push(value);
    }
  }
  return out;
}
