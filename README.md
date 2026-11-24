# RAG 知识库 + Agent 内容助手 · campus-kb + campus-portal

把媒体传讯处的规范、档案与往期公众号推文沉淀成 **RAG 知识库**，用 **Agent 助手**检索、组织内容，产出**可使用的微信公众号文章**。

> [!NOTE] 项目主线
> **检索知识库 → Agent 组织内容 → 生成可发布文章**。稿件规范校验只是这条链上的**一个功能**，不是项目定位。

- **campus-kb** —— 知识库与后端：规则引擎（19 条可溯源规则）、档案/推文语料、**段落分块 + BM25 + 本地 embedding 混合检索**、FastAPI、DeepSeek Agent；
- **campus-portal/web** —— React + TypeScript 前端：内容助手（Agent 对话）、校稿台（校验功能之一）、首页。

> 内部工具。仓库只包含代码、规则与自建样例，**不含任何原始规范文件**。

## 1. 要解决的问题

| 现状 | 后果 |
| --- | --- |
| 规范、档案、往期推文散落在共享文件夹和公众号 | 写一篇公众号文章要翻多处资料，口径难统一 |
| 同一份手册多版本在流转 | 引用口径不一致（`2026.05` / `20260618` 并存） |
| 规范文档自身存在矛盾 | 中文版「QS 第 63 位」，英文版写 `52rd`（应为 52nd） |
| 写作靠人肉逐条对照 | 漏检靠记忆，良品率不稳定 |

三条设计原则：**可执行**（规范写成 JSON 规则）、**可溯源**（回答与命中都带出处）、**不臆测**（查不到出处的内容不输出）。

## 2. 当前状态

| 模块 | 状态 | 说明 |
| --- | --- | --- |
| 规则引擎 `campus-kb` | ✅ 可用 | 19 条规则 / 8 个规则文件；坏样例命中 17 项，合规样例 0 误报 |
| RAG 语义检索 `api/rag.py` | ✅ 可用 | 50 份语料切成 771 个带起止行号的段落块；BM25（字符 2-gram）+ 本地 ONNX `bge-small-zh-v1.5` 向量，RRF 融合；模型缺失自动降级纯 BM25。向量索引按语料版本戳落盘，入库新文章自动重建 |
| 文章生成 `#/compose` | ✅ 可用 | 输入选题 → 检索知识库 → DeepSeek 成结构化草稿（标题/导语/分节正文/配图建议）→ 后端校验每段出处 + 发前规范检查；无依据段落明确标注，不臆测。`POST /api/compose`，真实密钥端到端验证通过 |
| 薄后端（FastAPI） | ✅ 可用 | `/api/review`、`/api/rules`、`/api/health`、`/api/search`、`/api/review-file`（docx）、`/api/chat`（DeepSeek）、`/api/agent`（Agent 工具调用）、`/api/compose`（文章生成），109 个 pytest 锁基线，见 [ADR-002](campus-portal/docs/adr-002-python-backend.md) |
| 公众号语料入库 | ✅ 可用 | `campus-kb/tools/fetch_wechat.py` 抓自有公众号推文转 `corpus/text/*_WX.txt`，`_WX` 标记来源；文字型直接提取，长图型用 macOS Vision OCR（`tools/ocr.swift`，切片拼接识别）。入库即可被 `/api/search` 与 Agent 检索，无需重启 |
| 校稿台前端 | ✅ 可用 | 三栏核对、筛选、忽略、键盘导航；可粘贴任意稿件、上传 docx 送审，按后端精确命中动态标红；档案检索接 `/api/search`，报告可下载为 Markdown |
| 首页 | ✅ 完成 | 导航 + 主体（左：标题与墨点入口；右：3D 稿件卡轮播）+ 底部；墨点指向 `#/assistant` |
| Agent 助手 `#/assistant` | ✅ 可用 | 单输入框的 Agent 对话：DeepSeek Function Calling 自选工具（查规范 / 查档案 / 校稿件），工具在后端确定性执行并回灌，前端展示回答 + 执行轨迹 + 依据。校验结论仍由规则引擎产出。已用真实密钥端到端验证 |
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
│   ├── api/                       # FastAPI 薄封装 + rag.py（分块 / BM25 / 向量混合检索）
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

路由为 hash 形式，无需服务端配置：`#/` 首页、`#/compose` 写文章、`#/desk` 校稿台、`#/assistant` 内容助手。

## 5. 前端做了什么

**首页 `#/`**

- 回归首页本分：顶部导航（首页 / 内容助手 / 校稿台）+ 主体 + 页脚，去掉了统计条、能力卡片、流程条；保留 hero 右栏的 3D 稿件卡轮播（NAME-001 / SOEV-002 / RANK-001 三个真实命中，5.6s 切换、悬停暂停、reduced-motion 降级）；
- 墨点是「内容助手」的入口：SVG 精灵保留呼吸 / 眨眼 / 瞳孔跟随，点击进 `#/assistant`；
- 首页文案讲项目定位——「写出能发的公众号文章」，不堆校验数字；校稿台是导航里的一项功能。

**Agent 助手 `#/assistant`**

- 单输入框对话，用户不必选工具。DeepSeek Function Calling 自己判断调用哪一个：
  - `search_rules` → 规则库检索（后端 `checker.load_rules()`）
  - `search_archive` → 档案库混合检索：BM25 + 语义向量（后端 `api/rag.py`）
  - `review_draft` → 规则引擎校验（后端 `checker.run()`，结论以此为准）
- 工具在后端**确定性执行**，结果作为 tool 消息回灌模型；模型只做意图判断与语言组织，不产出校验结论。循环上限 4 步，防止不收敛。
- 前端展示模型回答 + 执行轨迹（每步调用了什么、传了什么参数、返回哪些依据条目）；查不到直说没依据，不臆测。
- 密钥配置：复制 `campus-kb/.env.example` 为 `campus-kb/.env`，填入 `DEEPSEEK_API_KEY`；`.env` 已 gitignore。未配置时 `/api/agent` 返回 503 并提示，上游失败返回 502。
- 旧的单轮问答 `/api/chat` 保留兼容，前端已不再使用；通用 UI 设计提示词见根目录 `UI-DESIGN-PROMPT.md`。

**写文章 `#/compose`（主线功能）**

- 首页主 CTA「开始写文章」进入；输入选题（或点示例），一次请求拿到结构化草稿；
- 后端三段流水线（`api/compose.py`）：① 确定性检索——**整句选题走混合检索**（BM25 + 语义向量），从档案/往期推文取带文件名 + 起止行号的段落块编号 `A1..`，从规范取 `R1..`；整句结果充足时不再补逐词检索，避免「写一」「一篇」这类常见 2-gram 引入无关素材；② DeepSeek 以 JSON 模式成稿，每段必须带 `[A#]` 引用，素材不足写「（素材不足，待补充）」不许编造；③ 后端核对引用编号（无效引用/无出处段落都暴露），并跑规则引擎做发前检查；
- 发前检查用 `archive` 模式——公众号文章不是投稿件，跳过 SUB-* 投稿格式规则（标题格式/英文标注/内容分类），只保留 NAME/PUNCT 等内容规范；
- 前端展示草稿 + 每段引用标记 + 配图建议；「事实依据」列出被引用素材的文件与行号，可回溯；「发前检查」列规范命中；可复制/下载 Markdown；
- `POST /api/compose`：未配置密钥 503、上游失败 502。真实密钥端到端验证：产出标题/导语/3 节正文/3 条配图建议，`grounded=True`（所有段落有出处），发前检查 0 误报。

**校稿台 `#/desk`**

- 三栏：正文（命中标红、行号对齐）→ 问题清单（错误 / 警告 / 已忽略，j/k 导航）→ 依据（规则原文 + 出处）；
- 顶栏「粘贴稿件」送审任意正文，「上传 docx」走 `/api/review-file` 提取文本并校验；后端 finding 返回精确命中 `hit`，前端 `buildDraft` 据此切分标红，不再依赖内置样例；
- 「导出批注」在 docx 路径下真正下载 Markdown 报告（文件名沿用原稿，仅换后缀 `.md`）；
- 问题条目 key 为 `${ruleId}@${line}`，不用数组下标——筛选后下标会漂移；
- 同一段命中多条规则时，只要有一条 `error` 就按错误样式标记（警告淹没在错误里反而是误导）。

**设计语言**（通用提示词见根目录 `UI-DESIGN-PROMPT.md`）

- `tokens.css` 是颜色 / 字号 / 字距的唯一来源；
- 动效三铁律：默认样式可见、动画由运行态 class 驱动、一律提供 `prefers-reduced-motion` 降级；
- 不用 Tailwind——版式数值太具体（1px 描边 + 3px 外扩阴影），utility 反而难读，用 CSS Modules。

## 6. 工程约束

- TypeScript `strict`；ESLint 10 flat config 开 `recommendedTypeChecked`；
- Prettier 管格式，`eslint-config-prettier` 关掉 ESLint 冲突项；
- 测试：前端 72 个（Vitest + Testing Library，含写文章页 4 项），后端 109 个（pytest，含文章生成 15 项 + 语义检索 15 项）；单测默认关闭本地 embedding、用假向量注入，不依赖模型下载；
- 运行时依赖只有 React 本体 + FastAPI（docx 解析用 `python-docx`，文件上传用 `python-multipart`，AI 问答用 `httpx` + `pydantic-settings`）。

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
- **11-21 接入 DeepSeek**：保留三个零幻觉工具，新增第四项「AI 问答」。后端 `api/deepseek.py` 用字符 2-gram + 关键词打分从规则与档案检索片段，拼 system prompt 后经 `httpx` 调 DeepSeek OpenAI 兼容接口；`POST /api/chat` 未配置密钥 503、上游失败 502。前端新增 `postChat`、`answerFromChat` 与生成标记，明确与确定性结论区分。用户填入密钥后完成真实模型端到端验证：回答正确引用 `[S1]`/`[S3]`/`[S4]`，返回 9 条来源；浏览器实测生成标记、来源列表与免责声明均正常，console 无报错。
- **11-23 转 Agent + 明确主线**：按用户澄清，项目主线是 RAG 知识库 + Agent 助手，不是文稿校订。把助手从「四工具手动切换」重构为 Agent：后端 `api/agent.py` 用 DeepSeek Function Calling 自选 `search_rules` / `search_archive` / `review_draft`，工具在后端确定性执行并回灌，循环上限 4 步；`POST /api/agent` 返回回答 + 工具轨迹。前端助手改为单输入框对话并展示执行轨迹与依据，删除旧的 `assistantTools.ts` 死代码。真实密钥端到端验证三个工具均能自动选中并正确作答。通用 UI 设计整理为根目录 `UI-DESIGN-PROMPT.md`（非 skill）。前端 68 项 / 后端 43 项测试全绿。
- **11-23 公众号语料入库**：按用户「把自有公众号往期推文当 RAG 语料」的诉求，新增 `campus-kb/tools/fetch_wechat.py`——从 `#js_content` 提取段落、剔除「点击蓝字关注」等模板噪音、图片转 `[图N]` 占位并落本地（公众号 CDN 有 referer 防盗链，直链外站必裂）、元数据记入 `corpus/wechat-sources.json`；输出格式对齐 `corpus/text/*.txt`，检索侧零改动。首篇实测即为长图型推文（29 张切片，HTML 只有 158 字），故新增 `tools/ocr.swift` 走 macOS Vision 做中文 OCR（零三方依赖、离线），并用 `--stitch` 按累积高度拼接后识别以缓解切片接缝缺字，该篇找回约 2000 字。顺带修掉三处 Agent 检索缺陷：命中行带 ±2 行上下文（否则模型看不到相邻的「地点/开放时间」，会误答「档案未记载」）、多词 AND 空结果降级单关键词重试（模型习惯堆同义词导致全空）、语料缓存加文件版本戳（抓完文章无需重启进程）。真实端到端：Agent 从该推文答出咨询地点「学生公寓4栋1楼·芦苇渡」、24 小时热线 400-098-2525、紧急 110/120。后端 61 项测试全绿。
- **11-24 全量采集**：解决「怎么把整个公众号都抓下来」——公众号没有公开列表 API，新增 `campus-kb/tools/collect_links.js`，在后台「已发表」页面用登录态直接调同源接口翻页，浏览器自动带 cookie（不把登录态交给任何外部程序），兼容 `appmsgpublish` / `appmsg` 两套接口、自动过滤已删文章与视频号链接，产出 `urls.txt` 后接 `fetch_wechat.py --urls` 批量入库。配套改动：`wechat-sources.json` 改为逐篇落盘（原先整批结束才写，几百篇中途中断会全部重抓）；新增 `--drop-images`（OCR 落盘后清图，长图型每篇约 20MB）；解析逻辑补 10 项 node 测试（`node --test tools/collect_links.test.js`），其中「空响应」用例发现并修掉了 `parseLegacy` 对 `null` 未做保护的崩溃。
- **11-24 推文入库 11 篇**：按用户分两批给出的 10 个链接抓取，语料库现有 11 篇推文（约 2.2 万字），检索扫描量 27 → 37 份。10 篇均为文字型（HTML 直取），只有「压力值」一篇是长图型需 OCR。过程中发现并修掉一处**跨文档污染**：长图末尾的「推荐阅读 / 点击关注」卡片会被 OCR 进正文，导致在 A 文里能搜到 B 文的标题（实测「品鉴岭南」在《压力值》一文 L96 命中，还带出 `and Nanotechnology` 重复串）。新增 `truncate_tail`：遇到文末卡片标记即截断，该篇 98 行 2023 字 → 91 行 1897 字，污染清零，补 6 项测试。真实 Agent 验证两问：QS 排名答出「亚洲第 4、香港第 2」并**主动说明档案主体是香港城市大学整体、未单独区分东莞校区**（未顺着提问编造）；1000 万捐赠答出捐赠方森拓建设集团·黎建波与用途「未来智能中心」。
- **11-24 推文累计 24 篇**：第三批 14 条链接（其中 1 条与上批重复，自动跳过）入库 13 篇，全部为文字型，1 分钟跑完、0 失败。语料库现 **24 篇推文 / 约 5 万字**，检索扫描量 37 → 50 份。质量体检 24 篇：模板噪音 0（唯一命中「扫描二维码」的是《硕士申请指南》正文里的申请步骤，属正文非残留）、无重复串、无过短文件。Agent 三问全部准确：到访官员答「陈国基、10 月 24 日」并主动标注**档案未写年份**；顶尖科学家答「年度榜 41 位 / 终身榜 29 位」区分口径；申请截止答出三轮日期与申请平台域名。
- **11-24 逐篇入库通道**：用户拿不到公众号后台登录态，只能一篇篇复制链接，原「先导 `urls.txt` 再批量抓」的路径走不通。抓取工具改为接受**任意粘贴文本**：全局扫描 `mp.weixin.qq.com/s` 链接，标题、分享卡片、粘连无分隔、带 `?scene=1#rd` 追踪参数的都能解析；短链归一成规范形态，同一篇从不同入口复制多次只抓一遍。新增 `--paste`（读 stdin）与 `corpus` 外的累积收件箱 `inbox.txt`（不带任何参数时默认读它，已 gitignore），攒几条抓一次、已入库自动跳过。过程中修掉一个真 bug：整体正则贪婪匹配会吞掉相邻链接的 `https`，实测 4 条粘连链接只抽到 2 条，改为前缀与正文分开扫描。后端测试 67 → **79 项**（新增 12 项链接抽取与来源汇总测试）。
- **11-24 定位再明确 + 文章生成（主线落地）**：用户再次明确整体定位是「RAG 知识库 + Agent 助手 → 生成可使用的微信公众号文章」，规范校验只是其中一个功能；据此把全项目定位表述（README 三份、前端文案、模块 docstring、Agent system prompt）统一改正。随后实现 P0 主线功能：新增 `api/compose.py` 三段流水线（确定性检索素材编号 → DeepSeek JSON 模式成稿 → 后端校验出处 + 发前规范检查），`POST /api/compose`；前端新增 `#/compose` 写文章页（选题输入、结构化草稿预览、引用标记、配图建议、事实依据、发前检查、复制/下载 Markdown），首页主 CTA 改为「开始写文章」。真实调用暴露一个误报——发前检查把 SUB-* 投稿格式规则套到公众号文章上，改用 `archive` 模式跳过（公众号非投稿件）。真实密钥端到端验证：产出标题/导语/3 节正文/3 条配图建议，`grounded=True`、发前检查 0 误报。后端 79 → **94 项**、前端 68 → **72 项**。

- **11-24 P0 落地：RAG 语义检索（混合召回）**：用户「做 p0」。新增 `api/rag.py`：语料按行聚合成 771 个段落块（带 file + start_line/end_line，空行弱边界、超长行滑窗切、相邻块重叠一行），稀疏路纯 Python BM25（中文字符 2-gram）、稠密路本地 ONNX `fastembed` + `BAAI/bge-small-zh-v1.5`（512 维，不调外部 embedding API、无需额外密钥），两路按 RRF 融合；向量索引按语料版本戳落盘 `corpus/.index/`（gitignore），新增文章自动重建。`GET /api/search` 加 `mode`（hybrid 默认 / keyword / semantic / strict 旧 AND 回归对照），Agent 的 `search_archive` 与 `compose` 素材检索同步切到混合召回，compose 改为整句入检、只在结果不足时补词。模型缺失 / 下载失败 / `CAMPUS_EMBEDDING=off` 时自动降级纯 BM25，功能永不挂；测试用假向量注入并默认关模型，不依赖 95MB 下载。过程中修掉一个真 bug：分块最小长度会丢掉短文件（语料最短 14 字），导致文章生成素材为空。真实端到端：换词提问「学生心理辅导应该去哪里预约」hybrid 前三条全是心理相关（top1 命中地点 + 24 小时热线），纯 keyword 第三条混入「巡检机器人」；`/api/compose` 用「学生心理健康支持服务」选题产出 3 段全带出处的正文（含地点、开放时间、热线），`grounded=True`。后端 94 → **109 项**（新增 15 项）全绿。

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
- Agent / AI 问答依赖本地 `campus-kb/.env` 中的 `DEEPSEEK_API_KEY`（已 gitignore）；模型只做意图判断与语言组织，回答不替代规则引擎的确定性校验，且受检索质量限制；
- 语义检索依赖本地 ONNX 模型（约 95MB，首次自动下载到本机缓存）；下载失败或设 `CAMPUS_EMBEDDING=off` 时自动降级纯 BM25，接口不会挂。向量索引是语料的派生物、未入库，可随时重建；尚未接入 reranker 重排序；
- 公众号抓取只处理**自有账号**；长图型推文靠 Vision OCR 提取，存在少量形近字与切片接缝处的缺字，适合做检索语料，不适合直接引用出版；
- `layout.json` 只是排版参数，尚未接入文档生成。

## 9. 下一步（主线：RAG 知识库 + Agent → 生成公众号文章）

1. **RAG 检索升级（✅ 已完成）**：段落分块（771 块，带起止行号）+ 本地 ONNX embedding + BM25 混合召回 + RRF 融合；语义召回经真实对比验证（换词提问「学生心理辅导去哪预约」命中「心理咨询预约信息卡」，纯关键词则混入无关档案）。下一步可做 reranker 重排序与分块质量抽样评估。
2. **文章生成质量提升**：现已能产出可溯源草稿（✅ 完成）；下一步做多稿对比、段落级改写、按公众号风格微调语气，并接入成稿后的一键复核闭环。
3. **公众号历史语料持续入库**：批量抓取往期推文，补齐选题、口径与活动记录，让 Agent 的答案与生成文章有更厚的依据；对 OCR 文本做抽样校对，重点看长图接缝处与形近字。
4. **Agent 能力扩展**：增加只读工具（如规则版本对比、跨档案时间线），引入对话记忆持久化；稿件规范校验作为生成后的质量关卡继续保留。
5. 投稿流程与版本管理（数据模型要点见 [ADR-001](campus-portal/docs/tech-selection.md) 第四节；投稿流程见第五节分期）；
6. 如需在原 docx 上写真批注或处理扫描件，再单独立项。

## 10. 说明

- 规则条目来自媒体传讯处规范手册，**原始手册文件未入库**；
- `campus-kb/samples/` 中稿件为自建测试文本，人物与事件均为虚构。
