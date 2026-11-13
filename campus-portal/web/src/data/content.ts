import type { Draft, Issue, Rule } from '../types';

/**
 * 内容全部来自 campus-kb 的真实校验结果：
 * 稿件 samples/bad-draft.md → checker.py（19 条规则）→ 17 项命中（错误 11 / 警告 6）。
 * 接入后端时，这里替换为 `GET /api/drafts/:id/review` 的响应即可，组件层不动。
 */

export const RULES: readonly Rule[] = [
  {
    id: 'SUB-001',
    name: '标题格式',
    source: '电子通讯平台投稿须知 · 投稿字段',
    quote: '标题须按「【投稿部门】投稿内容」的格式填写，不得只写事件名称。',
  },
  {
    id: 'SUB-002',
    name: '英文标题标记',
    source: '电子通讯平台投稿须知 · 投稿字段',
    quote: '仅提交中文内容的稿件，须在英文标题末尾标注 [Chinese]。',
  },
  {
    id: 'SUB-003',
    name: '内容分类',
    source: '电子通讯平台投稿须知 · 内容分类',
    quote: '投稿须勾选以下分类之一：通知动态、活动预告、大学要闻、媒体报道、他山之石。',
  },
  {
    id: 'NAME-001',
    name: '校名首次出现用全称',
    source: '常用表述规范手册 2026.05 · 一、学校定位与基本信息',
    quote:
      '全称：香港城市大学（东莞）——在文章首次提及需要用全称。\n在稿件开头首次出现校名时，须使用全称。',
    note: '手册同时列出两个简称（港城莞 / 港城大（东莞））并注明后者「正式感更强，新闻稿件首选」。规则据此判定：问题不在简称本身，而在**首次出现即用简称**。',
  },
  {
    id: 'NAME-002',
    name: '中文括号须用全角',
    source: '常用表述规范手册 2026.05 · 一、学校定位与基本信息',
    quote: '英文名称请使用半角括号 ( )，括号前须空一格；中文内容使用全角括号（）。',
  },
  {
    id: 'TITLE-001',
    name: '职务称谓完整',
    source: '常用表述规范手册 2026.05 ·（2）校领导职务全称对照',
    quote:
      '使用「职务全称 + 姓名」的形式。后文可用「职务简称 + 姓名」或「姓 + 职务」。\n例：校长段宝岩院士、执行校长鲁春教授、副校长（学术）李娟教授。',
    note: '规则比对职务全称对照表，发现「副校长李娟」缺少「（学术）」限定，与手册示例不一致。',
  },
  {
    id: 'SOEV-002',
    name: '禁用「中、港、台」并列',
    source: '常用表述规范手册 2026.05 · 3. 港澳台与领土主权类描述',
    quote:
      '不得出现「中、港、台」「中、澳、台」「中、港、澳、台」之类的表述，应称为「海峡两岸暨香港」「海峡两岸暨澳门」「海峡两岸暨香港、澳门」。不使用「两岸三（四）地」的提法。',
  },
  {
    id: 'SOEV-004',
    name: '正式文件写明主权归属',
    source: '常用表述规范手册 2026.05 · 3. 港澳台与领土主权类描述',
    quote: '中国与中国台湾、中国香港、中国澳门地区同时出现时，不得将香港、澳门与中国并列提及。',
    note: '手册另处允许「来自香港、澳门、台湾地区的学生」为标准措辞，故本项定级为**警告**而非错误——同一手册内存在口径差异。',
  },
  {
    id: 'PUNCT-001',
    name: '中文语境用全角标点',
    source: '常用表述规范手册 2026.05 · 三、常用信息：数字与标点符号使用',
    quote: '英文语境使用半角标点（. , ; : "" () ? !）；中文语境对应使用全角。',
    note: '同一行多处命中合并为一条，避免同一规则重复列出稀释问题清单。',
  },
  {
    id: 'PUNCT-002',
    name: '数字与单位之间不加空格',
    source: '常用表述规范手册 2026.05 · 三、常用信息：数字与标点符号使用',
    quote: '数量与单位、量词之间不加空格，如「100余位」「300人」。',
  },
  {
    id: 'PUNCT-003',
    name: '日期用中文格式',
    source: '常用表述规范手册 2026.05 · 三、常用信息：数字与标点符号使用',
    quote: '中文稿件日期写作「2027年3月15日」，不写作 2027/03/15。',
  },
  {
    id: 'ENG-001',
    name: '英文序数词',
    source: '常用表述规范手册 2026.05 · 三、常用信息：英文使用规范',
    quote: '英文序数词须正确：1st / 2nd / 3rd / 4th … 52nd。',
    note: '手册英文版自身写作 **52rd**，属手册笔误。规则按正确语法判定，**不跟随手册错误**——否则会把错误固化成标准。',
  },
  {
    id: 'RANK-001',
    name: '排名数据一致性',
    source: '常用表述规范手册 2026.05 · 一、学校定位与基本信息（中英对照）',
    quote:
      '中文版：香港城市大学在 2027 年 QS 世界大学排名位列第 63 位。\n英文版：CityUHK ranks 52rd globally in the 2027 QS World University Rankings.',
    note: '手册中英文版本对同一排名给出 63 / 52 两个数值。规则只检出冲突并上报，**不自行判定哪个正确**——权威值须由媒体传讯处确认。',
  },
];

export const ISSUES: readonly Issue[] = [
  {
    key: 'SUB-001@1',
    ruleId: 'SUB-001',
    severity: 'error',
    line: 1,
    message: '标题未按「【投稿部门】投稿内容」格式填写',
    fix: '【媒体传讯处】2026 智慧城市与新材料论坛在校举行',
  },
  {
    key: 'SUB-002@1',
    ruleId: 'SUB-002',
    severity: 'error',
    line: 1,
    message: '仅提交中文内容，但英文标题未标注 [Chinese]',
    fix: '在英文标题末尾加 [Chinese]',
  },
  {
    key: 'SUB-003@1',
    ruleId: 'SUB-003',
    severity: 'warning',
    line: 1,
    message: '未声明内容分类（通知动态 / 活动预告 / 大学要闻 / 媒体报道 / 他山之石）',
    fix: '补充分类标记：活动预告',
  },
  {
    key: 'NAME-001@3',
    ruleId: 'NAME-001',
    severity: 'error',
    line: 3,
    message: '首次出现校名即使用简称「港城大（东莞）」',
    fix: '首次出现改为「香港城市大学（东莞）」，后文再用简称',
  },
  {
    key: 'PUNCT-001@3',
    ruleId: 'PUNCT-001',
    severity: 'error',
    line: 3,
    message: '中文语境使用了半角逗号「,」（共 1 处）',
    fix: '改用全角「，」',
  },
  {
    key: 'PUNCT-002@3',
    ruleId: 'PUNCT-002',
    severity: 'warning',
    line: 3,
    message: '数字与单位之间不应有空格「100 余位」',
    fix: '改为「100余位」',
  },
  {
    key: 'NAME-002@5',
    ruleId: 'NAME-002',
    severity: 'error',
    line: 5,
    message: '中文内容使用了半角括号「(东莞)」',
    fix: '改为「香港城市大学（东莞）」',
  },
  {
    key: 'PUNCT-001@5',
    ruleId: 'PUNCT-001',
    severity: 'error',
    line: 5,
    message: '中文语境使用了半角逗号「,」（共 2 处）',
    fix: '改用全角「，」',
  },
  {
    key: 'TITLE-001@5',
    ruleId: 'TITLE-001',
    severity: 'warning',
    line: 5,
    message: '「李娟」缺少规范职务限定（应为 副校长（学术））',
    fix: '副校长（学术）李娟教授',
  },
  {
    key: 'PUNCT-001@7',
    ruleId: 'PUNCT-001',
    severity: 'error',
    line: 7,
    message: '中文语境使用了半角逗号「,」（共 2 处）',
    fix: '改用全角「，」',
  },
  {
    key: 'SOEV-002@7',
    ruleId: 'SOEV-002',
    severity: 'error',
    line: 7,
    message: '出现「中、港、台」并列提法，违反领土主权类表述规范',
    fix: '改为「海峡两岸暨香港、澳门」',
  },
  {
    key: 'SOEV-004@7',
    ruleId: 'SOEV-004',
    severity: 'warning',
    line: 7,
    message: '「香港、澳门、台湾地区」未写明主权归属',
    fix: '中国香港、中国澳门和中国台湾地区',
  },
  {
    key: 'ENG-001@9',
    ruleId: 'ENG-001',
    severity: 'error',
    line: 9,
    message: '英文序数词错误「52rd」',
    fix: '52nd',
  },
  {
    key: 'PUNCT-001@9',
    ruleId: 'PUNCT-001',
    severity: 'error',
    line: 9,
    message: '中文语境使用了半角逗号「,」（共 3 处）',
    fix: '改用全角「，」',
  },
  {
    key: 'RANK-001@9',
    ruleId: 'RANK-001',
    severity: 'error',
    line: 9,
    message: '文内 QS 2027 排名出现两个数值 [63, 52]',
    fix: '须由媒体传讯处确认权威值后统一',
  },
  {
    key: 'PUNCT-002@9',
    ruleId: 'PUNCT-002',
    severity: 'warning',
    line: 9,
    message: '数字与单位之间不应有空格「300 人」',
    fix: '改为「300人」',
  },
  {
    key: 'PUNCT-003@9',
    ruleId: 'PUNCT-003',
    severity: 'warning',
    line: 9,
    message: '日期「2027/03/15」不符合中文格式',
    fix: '2027年3月15日',
  },
];

export const DRAFT: Draft = [
  {
    line: 1,
    isTitle: true,
    segments: [
      { text: '智慧城市与新材料论坛在校举行', issueKeys: ['SUB-001@1', 'SUB-002@1', 'SUB-003@1'] },
    ],
  },
  {
    line: 3,
    segments: [
      { text: '11月11日' },
      { text: ',', issueKeys: ['PUNCT-001@3'] },
      { text: ' ' },
      { text: '港城大（东莞）', issueKeys: ['NAME-001@3'] },
      {
        text: '与松山湖材料实验室联合举办的“2026智慧城市与新材料论坛”在校园举行。本次论坛吸引来自粤港澳大湾区高校的',
      },
      { text: '100 余位', issueKeys: ['PUNCT-002@3'] },
      { text: '学者参加。' },
    ],
  },
  {
    line: 5,
    segments: [
      { text: '香港城市大学(东莞)', issueKeys: ['NAME-002@5'] },
      { text: '校长段宝岩、执行校长鲁春、副校长' },
      { text: '李娟', issueKeys: ['TITLE-001@5'] },
      { text: '、协理副校长（运维）程军祥出席开幕式。段宝岩在致辞中表示' },
      { text: ',', issueKeys: ['PUNCT-001@5'] },
      { text: ' 学校将持续推动跨学科合作' },
      { text: ',', issueKeys: ['PUNCT-001@5'] },
      { text: ' 打造开放共享的科研平台。' },
    ],
  },
  {
    line: 7,
    segments: [
      { text: '论坛邀请来自' },
      { text: '香港、澳门、台湾地区', issueKeys: ['SOEV-004@7'] },
      { text: '的专家学者' },
      { text: ',', issueKeys: ['PUNCT-001@7'] },
      { text: ' 以及' },
      { text: '中、港、台', issueKeys: ['SOEV-002@7'] },
      {
        text: '三地的青年学者共同研讨。澳门大学(University of Macau)教授陈志强作主题报告。陈志强先生指出',
      },
      { text: ',', issueKeys: ['PUNCT-001@7'] },
      { text: ' 新材料是湾区产业升级的关键。' },
    ],
  },
  {
    line: 9,
    segments: [
      { text: '据了解' },
      { text: ',', issueKeys: ['PUNCT-001@9'] },
      { text: ' 香港城市大学（东莞）在2027年QS世界大学排名位列' },
      { text: '第63位', issueKeys: ['RANK-001@9'] },
      { text: ',', issueKeys: ['PUNCT-001@9'] },
      { text: ' 在QS 2027排名中位列' },
      { text: '52rd', issueKeys: ['ENG-001@9', 'RANK-001@9'] },
      { text: '。明年论坛拟于' },
      { text: '2027/03/15', issueKeys: ['PUNCT-003@9'] },
      { text: '举行' },
      { text: ',', issueKeys: ['PUNCT-001@9'] },
      { text: ' 预期规模扩大至' },
      { text: '300 人', issueKeys: ['PUNCT-002@9'] },
      { text: '。' },
    ],
  },
];
