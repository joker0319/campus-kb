# 校园媒体内容质量门 · campus-kb + 校稿台

把香港城市大学媒体传讯处的写作规范，从「共享文件夹里的 Word/PDF」变成「投稿前机器可执行、件件可溯源的检查」。

- **campus-kb** —— Python 规则引擎：19 条规则，全部来自规范原文，每条命中可回溯到章与条；
- **校稿台（campus-portal/web）** —— React + TypeScript 前端：粘一段正文即可看到命中与改法。

> 内部工具。仓库只包含代码、规则与自建样例，**不含任何原始规范文件**。

## 1. 要解决的问题

| 现状 | 后果 |
| --- | --- |
| 规范以 Word/PDF 存在共享文件夹 | 投稿前靠人肉逐条对照，漏检靠记忆 |
| 同一份手册多版本在流转 | 引用口径不一致（`2026.05` / `20260618` 并存） |
| 规范文档自身存在矛盾 | 中文版「QS 第 63 位」，英文版写 `52rd`（应为 52nd） |

三条设计原则：**可执行**（规范写成 JSON 规则）、**可溯源**（命中带出处）、**不臆测**（查不到出处的判定不输出）。

## 2. 当前状态

| 模块 | 状态 | 说明 |
| --- | --- | --- |
| 规则引擎 `campus-kb` | ✅ 可用 | 19 条规则 / 8 个规则文件；坏样例命中 17 项，合规样例 0 误报 |
| 薄后端（FastAPI） | ✅ 可用 | `/api/review`、`/api/rules`、`/api/health`、`/api/search`、`/api/review-file`（docx），31 个 pytest 锁基线，见 [ADR-002](campus-portal/docs/adr-002-python-backend.md) |
| 校稿台前端 | ✅ 可用 | 三栏核对、筛选、忽略、键盘导航；可粘贴任意稿件、上传 docx 送审，按后端精确命中动态标红；档案检索接 `/api/search`，报告可下载为 Markdown |
| 首页 | ✅ 完成 | 导航 + 主体（左：标题与墨点入口；右：3D 稿件卡轮播）+ 底部；墨点指向 `#/assistant` |
| 助手页 `#/assistant` | ✅ 可用 | 三项确定性工具已接本地接口：问规范（`/api/rules` 关键词筛选）、查档案（`/api/search`）、校稿件（`/api/review`）；逐条给出处，查不到直说，不接大模型、不臆测 |
| 前端部署（Vercel） | ✅ 静态站 | Vercel 导入 `campus-portal/web`，Root Directory 设为 `campus-portal/web`（见该目录 `vercel.json`）；仅前端，线上无 `/api` 后端 |
| 数据库 / 投稿流程 | ⏳ 未开始 | 选型见 [ADR-001](campus-portal/docs/tech-selection.md) |
| docx 解析 / 导出报告 | ✅ 可用 | 上传 `.docx` 提取段落与表格文本，按同一套规则校验并给出处；导出 Markdown 报告。不在原文件写真批注 |

引擎实测（`campus-kb/samples/`，可复现）：

| 场景 | 结果 |
| --- | --- |
| `bad-draft.md`（埋 12 处典型错误） | 命中 **17 项**：错误 11 / 警告 6 |
| `good-draft.md`（完全合规） | 命中 **0 项**，零误报 |
| `University of Macau` 专有名词 | 正确跳过，未被 `Macau → Macao` 误伤 |

## 3. 目录结构

```
.
├── campus-kb/                     # 规则引擎 + FastAPI 薄后端
│   ├── checker.py                 # 引擎：加规则只改 JSON，不改代码
│   ├── api/                       # FastAPI 封装：/api/review、/api/rules、/api/health、/api/search
│   ├── tests/                     # pytest：契约 + bad 17 / good 0 基线断言
│   ├── rules/                     # 8 个规则文件
│   ├── samples/                   # 正反样例
│   └── reports/                   # 生成的 Markdown 报告样例
├── campus-portal/
│   ├── docs/                      # ADR-001 技术选型 / ADR-002 后端语言
│   ├── prototype/                 # 早期静态原型
│   └── web/                       # React 19 + TS + Vite 前端
│       ├── src/pages/             # Landing（首页）、Desk（校稿台）、Assistant（助手壳）
│       ├── src/components/        # 三栏校稿台、CaseStage（首页 3D 轮播）、PetMascot（助手入口）、SubmitDialog
│       ├── src/lib/               # review / segments / buildDraft / api / countUp 纯函数
│       └── src/styles/            # tokens.css 单一来源 + CSS Modules
└── .workbuddy/skills/campus-design-language/   # 设计语言规范
```

## 4. 快速开始

### 4.1 规则引擎 / 后端

```bash
cd campus-kb
python3 checker.py samples/bad-draft.md                 # 终端输出（退出码：有 error 返回 1）
python3 checker.py samples/bad-draft.md --json          # 供其他系统调用
uv sync                                                 # 安装 API 依赖
uv run pytest                                           # 27 个用例，含基线断言
uv run uvicorn api.main:app --reload --port 8000        # 启动 API
```

### 4.2 前端

```bash
cd campus-portal/web
npm install
npm run dev        # http://127.0.0.1:5173
npm run check      # 类型 + ESLint + Prettier + 测试，提交前跑这个
```

路由为 hash 形式，无需服务端配置：`#/` 首页、`#/desk` 校稿台、`#/assistant` 助手页。

## 5. 前端做了什么

**首页 `#/`**

- 回归首页本分：顶部导航（首页 / 助手 / 校稿台）+ 主体 + 页脚，去掉了统计条、能力卡片、流程条；保留 hero 右栏的 3D 稿件卡轮播（NAME-001 / SOEV-002 / RANK-001 三个真实命中，5.6s 切换、悬停暂停、reduced-motion 降级）；
- 墨点是「知识库的个人助手」的入口：SVG 精灵保留呼吸 / 眨眼 / 瞳孔跟随，点击进 `#/assistant`；
- 首页文案只讲定位，不堆校验数字（「规范、档案与稿件检查，都从一个入口进去」）。

**助手页 `#/assistant`**

- 三项确定性工具已接本地接口：问规范（`/api/rules` 关键词筛选）、查档案（`/api/search`）、校稿件（`/api/review`）；
- 对话式界面，每条回答带规则号 / 行号 / 出处 / 改法；查不到直说「未找到，不做臆测」，不接大模型。


**校稿台 `#/desk`**

- 三栏：正文（命中标红、行号对齐）→ 问题清单（错误 / 警告 / 已忽略，j/k 导航）→ 依据（规则原文 + 出处）；
- 顶栏「粘贴稿件」送审任意正文，「上传 docx」走 `/api/review-file` 提取文本并校验；后端 finding 返回精确命中 `hit`，前端 `buildDraft` 据此切分标红，不再依赖内置样例；
- 「导出批注」在 docx 路径下真正下载 Markdown 报告（文件名沿用原稿，仅换后缀 `.md`）；
- 问题条目 key 为 `${ruleId}@${line}`，不用数组下标——筛选后下标会漂移；
- 同一段命中多条规则时，只要有一条 `error` 就按错误样式标记（警告淹没在错误里反而是误导）。

**设计语言**（`.workbuddy/skills/campus-design-language/`）

- `tokens.css` 是颜色 / 字号 / 字距的唯一来源；
- 动效三铁律：默认样式可见、动画由运行态 class 驱动、一律提供 `prefers-reduced-motion` 降级；
- 不用 Tailwind——版式数值太具体（1px 描边 + 3px 外扩阴影），utility 反而难读，用 CSS Modules。

## 6. 工程约束

- TypeScript `strict`；ESLint 10 flat config 开 `recommendedTypeChecked`；
- Prettier 管格式，`eslint-config-prettier` 关掉 ESLint 冲突项；
- 测试：前端 71 个（Vitest + Testing Library），后端 31 个（pytest）；
- 运行时依赖只有 React 本体 + FastAPI（docx 解析用 `python-docx`，文件上传用 `python-multipart`）。

## 7. 开发日志

- **11-11 规则引擎**：三份规范拆成 19 条规则；首跑即发现规范自身矛盾（QS 排名中英不一致、版本号并存）。原则：规则只报告冲突，权威值由传讯处确认。
- **11-11 技术选型**：定前后端分离方案（ADR-001）。
- **11-12 原型三轮**：v1 全页 mosaic 被判「AI 味太重」，v3 定型。
- **11-13 React 落地**：首页与校稿台从零实现，测试从 0 到 39。
- **11-18 后端**：后端语言定为 Python（ADR-002），FastAPI 封装引擎并锁基线。
- **11-20 梳理**：清理目录与文档。
- **11-20 任意稿件**：后端 finding 增加精确 `hit`，前端按 `hit` 动态标红；校稿台支持粘贴任意正文送审。
- **11-20 首页改版**：首页回归导航 + 主体 + 底部，去掉校验罗列；墨点改为「知识库的个人助手」入口；新增 `#/assistant` 界面壳（能力待接入）。3D 轮播按用户要求保留在 hero 右栏原位置。
- **11-21 助手接接口**：三项工具接本地 `/api/rules`、`/api/search`、`/api/review`，确定性路由、逐条给出处，不接大模型。Vercel 部署问题排查后按用户要求终止上线。
- **11-21 docx 闭环**：后端 `POST /api/review-file` 用 `python-docx` 提取段落/表格文本并复用同一套规则，返回命中与 Markdown 报告；前端加上传入口与下载按钮。真实浏览器端到端验证：17 项命中（错误 11 / 警告 6）、19 处标红、报告下载文件名正确。

踩过的坑（均已写进代码注释或测试）：

| 现象 | 根因 | 处理 |
| --- | --- | --- |
| 整页白屏 | `opacity: 0` 写在默认样式，运行态 class 移除后元素落回透明 | 隐藏态只挂 `[data-run='true']` 下 |
| 入场动画全页失效 | CSS 挂 `.root[data-run]`，实际元素类名是 `.page` | 改成 `.page[data-run='true']` |
| 类名不生效 | TSX 用字面量 `"in"`，CSS Modules 会 hash | 一律 `s.in` |
| 测试多次命中元素 | 未开 `globals` 时 Testing Library 不自动 cleanup | `setup.ts` 加 `afterEach(cleanup)` |
| 小助手放大后几乎没变 | SVG `viewBox` 留白，放大的是透明区 | viewBox 裁到图形本身 |
| 悬停后轮播永久停住 | 移出只回正 3D 倾斜，没恢复定时器 | 移出解除暂停，假计时器测试锁住 |

## 8. 已知限制

- 只做**文本规则**：不判断事实真伪，不校验图片（仍需人工）；
- 中文分词靠正则，长句中的职务简称（如「段校长」）可能漏判，靠人名 + 窗口匹配兜底；
- docx 支持正文提取与报告导出，但不在原 `.docx` 上写真批注（只输出 Markdown 报告）；扫描件 PDF 仍需人工/OCR；
- `layout.json` 只是排版参数，尚未接入文档生成。

## 9. 下一步

1. 投稿流程与版本管理（模型要点见 ADR-001 第四节）；
2. 带出处的规范问答、初稿生成；
3. 如需在原 docx 上写真批注或处理扫描件，再单独立项。

## 10. 说明

- 规则条目来自媒体传讯处规范手册，**原始手册文件未入库**；
- `campus-kb/samples/` 中稿件为自建测试文本，人物与事件均为虚构。
