/**
 * 首页轮播的三个案例，全部取自 campus-kb/samples/bad-draft.md 的真实命中，
 * 规则号与出处来自 rules/*.json，未做改写或美化。
 */
export interface CaseItem {
  id: string;
  name: string;
  /** 原稿行号 */
  line: number;
  before: string;
  hits: readonly string[];
  after: string;
  why: string;
  source: string;
}

/* 非空元组：保证索引访问时至少有一项，避免调用方到处做 undefined 判断 */
export const CASES: readonly [CaseItem, ...CaseItem[]] = [
  {
    id: 'NAME-001',
    name: '校名首次出现用全称',
    line: 3,
    before: '港城大（东莞）与松山湖材料实验室联合举办的论坛在校园举行。',
    hits: ['港城大（东莞）'],
    after: '香港城市大学（东莞）与松山湖材料实验室……',
    why: '首次出现须用全称，简称放全角括号内；后文才可用简称。',
    source: '《常用表述规范手册》一、学校定位与基本信息',
  },
  {
    id: 'SOEV-002',
    name: '禁用「中、港、台」并列',
    line: 7,
    before: '以及中、港、台三地的青年学者共同研讨。',
    hits: ['中、港、台'],
    after: '以及海峡两岸暨香港的青年学者共同研讨。',
    why: '港澳台不得与中国并列，应写「海峡两岸暨香港」。',
    source: '《常用表述规范手册》3. 港澳台与领土主权类描述',
  },
  {
    id: 'RANK-001',
    name: '排名须与权威口径一致',
    line: 9,
    before: '在2027年QS世界大学排名位列第63位，在QS 2027排名中位列52rd。',
    hits: ['第63位', '52rd'],
    after: '统一为「第52位」（20260618 版权威口径）。',
    why: '媒体传讯处已裁决：以 20260618 版第 52 位为准；第 63 位与 52rd 属旧版/副本错误，规则现在直接判错。',
    source: '《常用表述规范手册 20260618》· 三、排名相关',
  },
];
