/**
 * 首页轮播：按项目定位组织「RAG 知识库 → Agent 成稿 → 可直发公众号文章」三帧。
 * 数字取自 campus-kb 的真实统计，链路与端点均对应现有实现；
 * 规范校验只是链路里的一环，不再是首页主角。
 */
export interface StageItem {
  id: string;
  /** 卡堆左侧的两位序号 */
  step: string;
  phase: string;
  name: string;
  lead: string;
  points: readonly string[];
  /** 这一帧交付给用户看的东西 */
  output: string;
  note: string;
  source: string;
}

export const CASES: readonly [StageItem, ...StageItem[]] = [
  {
    id: 'STAGE-01',
    step: '01',
    phase: '知识库',
    name: '语料进库，先有据可查',
    lead: '规范手册、学校档案与往期公众号推文统一入库，切块后建混合检索索引。',
    points: [
      '67 篇语料 · 14.2 万字，1144 个检索块',
      'BM25 关键词 + 向量语义，命中带文件名与行号',
      '672 张配图按内容哈希归档，397 张可推给编辑',
    ],
    output: '检索结果直接作为成稿依据，段落末尾标 [A1][A3] 可回溯',
    note: '素材库里没有的事实不写，宁可标注「素材不足，待补充」。',
    source: 'campus-kb/corpus · INDEX.md',
  },
  {
    id: 'STAGE-02',
    step: '02',
    phase: 'Agent 成稿',
    name: '一句话选题，边写边出稿',
    lead: 'Agent 按选题检索素材、自动判断文体，用流式输出把文章逐字铺开。',
    points: [
      '新闻动态 / 喜讯捷报 / 致辞讲稿，可自动判断',
      '标题 · 导语 · 小标题 · 正文，一次产出完整结构',
      '0.75s 给出文体、约 1.2s 出现第一个字',
    ],
    output: '成稿同时返回引用核对、发前检查与配图占位',
    note: '接口：POST /api/compose/stream，meta → delta → done。',
    source: 'campus-kb/api/compose.py · SSE 流式成稿',
  },
  {
    id: 'STAGE-03',
    step: '03',
    phase: '可直发',
    name: '复制排版，直接进公众号编辑器',
    lead: '同时产出内联样式 HTML 与 Markdown，样式不依赖 class，粘过去就是排好版的文章。',
    points: [
      '标题居中、小标题带主色竖线、正文两端对齐',
      '配图只用占位块，需要原图时再点「取原图」',
      '发前检查一并给出：规范命中、引用、职务与港澳台口径',
    ],
    output: '复制排版 → 粘贴 → 一篇能直接发出的公众号文章',
    note: '校稿只是其中一个环节，终点是可用成稿，不是一份检查报告。',
    source: 'campus-kb/api/export_html.py · rules/*.json',
  },
];
