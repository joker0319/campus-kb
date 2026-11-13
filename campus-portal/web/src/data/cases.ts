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
    name: '同一排名不得有两个数值',
    line: 9,
    before: '在2027年QS世界大学排名位列第63位，在QS 2027排名中位列52rd。',
    hits: ['第63位', '52rd'],
    after: '只保留一个权威值，由传讯处确认后再改。',
    why: '两个版本给出不同数值，规则只报冲突，不替人拍板。',
    source: '手册中英文版本对照 · 63 vs 52rd',
  },
];
