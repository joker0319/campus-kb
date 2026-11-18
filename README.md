# 校园媒体内容质量门 · campus-kb + 校稿台

把香港城市大学媒体传讯处的写作规范，从「存在共享文件夹里的 Word/PDF」变成「投稿前机器能执行、件件可溯源的检查」。

两条主线：

- **campus-kb** —— Python 规则引擎，19 条规则，全部来自规范原文，每条命中都能指回章与条；
- **校稿台（campus-portal/web）** —— React + TypeScript 前端，通讯员粘一段正文就能看到命中与改法。

> 内部工具。仓库只包含代码、规则与自建样例，**不含任何原始规范文件**。

---

## 1. 要解决的问题

现状的痛点不是「没有规范」，而是：

| 现状 | 后果 |
| --- | --- |
| 规范以 Word/PDF 存在共享文件夹 | 投稿前靠人肉逐条对照，漏检靠记忆 |
| 同一份手册多版本在流转 | 引用口径不一致（`2026.05` / `20260618` 并存） |
| 规范文档自身存在矛盾 | 中文版「QS 第 63 位」、英文版写 `52rd`（应为 52nd） |

所以工具的三条设计原则是：

1. **可执行** —— 规范写成 JSON 规则，不写在人的脑子里；
2. **可溯源** —— 每处命中都带出处（哪份文件、哪一条），点一下能回到原文；
3. **不臆测** —— 查不到出处的判定，系统不输出。

## 2. 当前状态

| 模块 | 状态 | 说明 |
| --- | --- | --- |
| 规则引擎 `campus-kb` | ✅ 可用 | 19 条规则 / 8 个规则文件；坏样例命中 17 项，合规样例 0 误报 |
| 薄后端（FastAPI） | 🟡 首版可用 | `/api/review`、`/api/rules`、`/api/health`，10 个 pytest 用例锁基线；决策见 [ADR-002](campus-portal/docs/adr-002-python-backend.md) |
| 校稿台前端 | 🟡 界面完成，数据为内置样例 | 三栏核对、筛选、忽略、键盘导航均已实现；接口未接 |
| 首页 | ✅ 完成 | 3D 稿件卡轮播（3 个真实命中案例）、墨点小助手、实测数据条 |
| 后端 / 数据库 | ⏳ 数据库未开始 | 后端已定 Python（FastAPI），见 [ADR-002](campus-portal/docs/adr-002-python-backend.md) |
| docx 上传解析 / 导出带批注文件 | ⏳ 未开始 | 目前只支持粘贴纯文本 |
| 模板填槽出初稿 | ⏳ 规划中（P1） | 依赖后端与 LLM 出网条件 |

规则引擎的实测数据（可复现，`campus-kb/samples/`）：

| 场景 | 结果 |
| --- | --- |
| `bad-draft.md`（埋了 12 处典型错误） | 命中 **17 项**：错误 11 / 警告 6 |
| `good-draft.md`（完全合规） | 命中 **0 项**，零误报 |
| `University of Macau` 专有名词 | 正确跳过，未被 `Macau → Macao` 误伤 |

## 3. 目录结构

```
.
├── campus-kb/                     # 规则引擎 + FastAPI 薄后端（校验的唯一事实来源）
│   ├── checker.py                 # 引擎：加规则只改 JSON，不改代码
│   ├── api/                       # FastAPI 封装：/api/review、/api/rules、/api/health
│   ├── tests/                     # pytest：契约 + bad 17 / good 0 基线断言
│   ├── rules/                     # naming / title / sovereignty / punctuation /
│   │                              # english / submission / rank / layout
│   ├── samples/                   # bad-draft.md / good-draft.md
│   └── reports/                   # 生成的 Markdown 报告样例
├── campus-portal/
│   ├── docs/tech-selection.md     # ADR-001：技术选型、内网约束、部署架构、分期计划
│   ├── prototype/                 # 早期静态原型（v3 校稿台 / v1 备档）
│   └── web/                       # React 19 + TS + Vite 前端
│       ├── src/pages/             # Landing（首页）、Desk（校稿台）
│       ├── src/components/        # Shell / DocumentPane / IssueList / EvidencePane
│       │                          # CaseStage（3D 卡轮播）/ PetMascot（小助手）
│       ├── src/lib/               # review（纯函数）/ segments / countUp
│       └── src/styles/            # tokens.css 单一来源 + 各页 CSS Modules
└── .workbuddy/skills/campus-design-language/   # 本项目设计语言（skill 形式沉淀）
```

## 4. 快速开始

### 4.1 规则引擎

```bash
cd campus-kb
python3 checker.py samples/bad-draft.md                # 终端输出
python3 checker.py samples/bad-draft.md --md out.md    # Markdown 报告
python3 checker.py samples/bad-draft.md --json         # 供其他系统调用
```

退出码：存在 `error` 时返回 `1`，可直接接 CI 或投稿平台的前置校验。无第三方依赖。

### 4.2 后端（FastAPI）

```bash
cd campus-kb
uv sync                                        # fastapi / uvicorn / pytest / httpx
uv run pytest                                  # 10 个用例，含 bad 17 / good 0 基线
uv run uvicorn api.main:app --reload --port 8000
```

### 4.3 前端

```bash
cd campus-portal/web
npm install
npm run dev      # http://127.0.0.1:5173
```

| 命令 | 作用 |
| --- | --- |
| `npm run dev` | 本地开发（Vite 6，显式绑 `127.0.0.1`，见 `vite.config.ts` 注释） |
| `npm run build` | `tsc --noEmit` + 生产构建 |
| `npm run check` | 类型 + ESLint + Prettier + 测试，提交前跑这个 |

路由是 hash 形式，无需服务端配置：`#/` 首页、`#/desk` 校稿台。

## 5. 前端做了什么

**首页 `#/`**

- 3D 稿件卡轮播：纯 CSS 3D（无 three.js），两张 ghost 深度层 + 主卡，轮播 NAME-001 / SOEV-002 / RANK-001 三个真实命中，5.6s 自动切换、悬停暂停、圆点可切，reduced-motion 下关闭倾斜与自动播放；
- 墨点小助手：SVG 精灵，呼吸 / 眨眼 / 瞳孔跟随指针，点一下换一条**真实**校验提示（不写无信息的可爱话）；
- 数据条：9 / 19 / 17 / 0 四个数字全部来自 `campus-kb` 实测。

**校稿台 `#/desk`**

- 三栏：正文（命中处标红、行号对齐）→ 问题清单（错误/警告/已忽略，j/k 或 ↑↓ 导航）→ 依据（规则原文引用 + 出处）；
- 问题条目的稳定 key 是 `${ruleId}@${line}`，不用数组下标——筛选后下标会漂移，忽略状态会串行；
- 同一段文字命中多条规则时，只要有一条是 `error` 就按错误样式标记（警告淹没在错误里反而是误导）。

**设计语言**（`.workbuddy/skills/campus-design-language/`）

- `tokens.css` 是颜色/字号/字距的唯一来源，组件只消费变量；
- 动效三条铁律：默认样式必须可见（隐藏态只挂在运行态选择器下）、动画由运行态 class 驱动、一律提供 `prefers-reduced-motion` 降级；
- 不用 Tailwind —— 这套版式的数值太具体（如 1px 描边 + 3px 外扩阴影），utility 反而更难读。用 CSS Modules。

## 6. 工程约束

- TypeScript `strict`，ESLint 10 flat config 开 `recommendedTypeChecked`（类型感知，能抓 `no-floating-promises` 这类纯语法规则抓不到的）；
- Prettier 管格式，ESLint 用 `eslint-config-prettier` 关掉冲突项；
- 测试 39 个（Vitest + jsdom + Testing Library）：纯函数 21、组件交互 18；
- 无运行时第三方依赖，除 React 本体。

## 7. 开发日志

**2026-11-11 · 规则引擎先行**

- 读三份规范（《常用表述规范手册》《报送模板》《投稿须知》），拆成 19 条规则写入 8 个 JSON；
- 第一次跑就把规范自己的毛病抖出来了：QS 排名中英版不一致（63 vs `52rd`）、文件名版本号 `20260618` 与封面 `2026.05` 不一致、存在 `(2)` 副本；
- 决定：规则只报告冲突，不替人拍板——权威值由传讯处确认。

**2026-11-11 · 技术选型**

- 定 React 19 + NestJS + PostgreSQL/pgvector + MinIO + BullMQ 的内网方案，写进 ADR-001；
- 关键判断：即使只有 CPU、不能出网，19 条规则 + 全文检索已经是完整可用的产品，生成是加分项不是地基。

**2026-11-12 · 原型三轮**

- v1 是全页 mosaic，被判定「AI 味太重」（紫粉渐变、光斑、逐字入场）；
- v2 收成三联校稿台，v3 定型并保留为 `prototype/`。

**2026-11-13 · React 落地**

- 前端从零实现首页与校稿台，测试从 0 到 39，全部通过；
- 首页迭代：hero 大标题与 lede 全部删掉（信息密度靠组件承担，不靠口号），小助手放大并占据原 lede 位置，轮播卡放大到主视觉尺度。

**踩过的坑（都写进代码注释了）**

| 现象 | 根因 | 处理 |
| --- | --- | --- |
| 整页白屏 | `opacity: 0` 写在默认样式，运行态 class 900ms 后移除，元素落回透明 | 隐藏态只挂 `[data-run='true']` 下，boot 脚本提前到 `<head>` |
| 入场动画全页失效 | CSS 挂 `.root[data-run]`，实际元素类名是 `.page` | 改成 `.page[data-run='true']` |
| 类名不生效 | TSX 里用了字面量 `"in"`，CSS Modules 会 hash | 一律 `s.in` |
| 测试多次命中元素 | 未开 `globals` 时 Testing Library 不自动 cleanup | `setup.ts` 加 `afterEach(cleanup)` |
| 小助手放大后几乎没变 | SVG `viewBox="0 0 64 64"`，图形只占约一半面积，放大的是透明区 | viewBox 裁到图形本身 |
| 悬停后轮播永久停住 | 移出只回正 3D 倾斜，没恢复定时器 | 移出同时解除暂停，并用假计时器写测试锁住 |

## 8. 已知限制

- 只做**文本规则**：不判断内容事实真伪，也不校验图片合规（仍需人工）；
- 中文分词靠正则，长句中的职务简称（如「段校长」）可能漏判，目前靠人名 + 窗口匹配兜底；
- 校稿台的数据是内置样例（`src/data/content.ts`），接后端时替换为 `GET /api/drafts/:id/review` 的响应即可，组件层不用动；
- `layout.json` 只是排版参数，尚未接入文档生成。

## 9. 下一步

1. **前端接后端**：`data/content.ts` 换成调 `/api/review`（FastAPI 已就绪），OpenAPI 生成前端类型；
2. **投稿链路**：docx 上传解析、导出带批注的 docx、三审三校流水；
3. **检索增强**：规范原文入库，支持「这条规范怎么写的」问答并带出处；
4. **闭环**：审核不通过的原因回流，补充规则。

完整的阶段划分与验收标准见 [`campus-portal/docs/tech-selection.md`](campus-portal/docs/tech-selection.md)。

## 10. 说明

- 代码按内部工具开发，规则条目来自媒体传讯处的规范手册，**原始手册文件未入库**；
- `campus-kb/samples/` 中的稿件为自建测试文本，人物与事件均为虚构。
