# 内容助手 · 前端

「RAG 知识库 + Agent 内容助手 → 生成公众号文章」项目的前端（React + TS）：首页、写文章（主线）、内容助手（Agent 对话）、校稿台（校验功能之一）四个页面。

## 运行

```bash
npm install
npm run dev        # http://127.0.0.1:5173
npm run build      # 类型检查 + 生产构建 → dist/
npm test           # 72 个用例（含写文章页与真实接口夹具测试）
npm run lint       # ESLint（含类型感知规则）
npm run format     # Prettier 格式化
npm run check      # 类型 + lint + 格式 + 测试，提交前跑这个
```

## 代码规范

- **ESLint 10**（flat config）：`typescript-eslint` 的 `recommendedTypeChecked`，
  开类型感知；外加 `react-hooks` v7。
- **Prettier 3**：格式规则全交给 Prettier，`eslint-config-prettier` 关掉 ESLint 冲突项。
- `.vscode/settings.json` 已配好保存时格式化 + 自动修 ESLint 可修项，
  装两个推荐扩展（ESLint、Prettier）即可。

## 结构

```
src/
  App.tsx               hash 路由：#/ 首页 · #/compose 写文章 · #/desk 校稿台 · #/assistant 助手
  pages/Landing.tsx     首页（导航 + 主体 + 底部，动效编排）
  pages/Compose.tsx     写文章（选题输入 → 结构化草稿 → 出处/检查 → 复制/下载）
  pages/Desk.tsx        校稿台（克制模式）
  pages/Assistant.tsx   Agent 助手（单输入框，模型自选工具，展示执行轨迹）
  types.ts              领域模型（Issue 用 `${ruleId}@${line}` 作稳定 key）
  data/content.ts       送审稿件与规则出处（依据栏）；命中不再内置
  lib/review.ts         纯函数：筛选、计数、键盘导航、标记严重度
  lib/api.ts            /api/review + /api/review-file + /api/agent + /api/compose：映射、收敛、Agent 对话、文章生成
  lib/segments.ts       按命中词切分正文（split + 捕获组，比 replace 安全）
  lib/buildDraft.ts     任意正文 + 后端精确 hit → 带 issueKeys 的 Draft（动态标红）
  lib/countUp.ts        数字滚动（进度钳制，防 rAF 负时间差）
  hooks/useReview.ts    useReducer 状态机（选中/筛选/忽略/导航）
  hooks/useReviewRequest.ts  校验请求：loading/ready/error + 重试/取消 + 粘贴/上传 docx 换稿
  hooks/useMediaQuery.ts
  components/           Shell(AppBar/Rail/StatusBar/Tabs)、DocumentPane、IssueList、EvidencePane
                        CaseStage（首页 3D 稿件卡轮播）、PetMascot（墨点 → 助手入口）
                        CorpusSearch（档案检索抽屉）、SubmitDialog（粘贴稿件弹窗）
  styles/tokens.css     设计 token 唯一来源
  styles/*.module.css   各页样式
```

## 与后端的接口

校稿台启动即 `POST /api/review`（正文来自 `DRAFT_TEXT`），命中经 `lib/api.ts` 映射为 `Issue[]`；
后端 key `ruleId@line` 与正文片段标注直接对齐，组件层不用改。
顶栏「粘贴稿件」可送审任意正文：「上传 docx」走 `POST /api/review-file`，后端提取段落/表格文本并复用同一套规则，返回命中与 Markdown 报告。
后端每条 finding 返回精确命中子串 `hit`，前端 `lib/buildDraft.ts`
按行号与 `hit` 切分正文、挂上 `issueKeys`，因此新稿件也能逐处标红并点回依据，不依赖内置样例。
docx 路径下「导出批注」会把报告下载为 `.md`（文件名沿用原稿）。
Vite 开发代理把 `/api` 转发到 `127.0.0.1:8000`（FastAPI）。
左栏「资源」打开档案检索抽屉，调 `GET /api/search`；助手页调 `POST /api/agent`（需后端配置 `DEEPSEEK_API_KEY`）——模型自选 `search_rules` / `search_archive` / `review_draft` 三个工具，工具在后端确定性执行，前端展示回答 + 执行轨迹 + 依据，校验结论以规则引擎为准。旧的 `/api/chat` 保留兼容但前端已不使用。
接口失败显示错误态与「重试」，不回落假数据；测试用 `src/test/fixtures/review.json`（真实 API 响应）mock fetch。

## 刻意的取舍

- **CSS Modules 而非 Tailwind**：设计值是精调的 px（15px 正文、1.95 行高、2px 校样下划线），
  塞进 Tailwind 会变成一堆 arbitrary value，改一处要翻三处。
- **字体全部系统栈**：不引外链字体，避免 fallback 导致度量失配。
- **正文不随视口缩放**：工作台不是落地页，13 寸与 27 寸上正文都必须是 15px。
- **入场动画的隐藏起始态只挂在运行态 class 下**：若写进默认样式，动画结束移除 class 后
  元素会回落到隐藏态（整页白屏）。

## 响应式

| 宽度       | 布局                                    |
| ---------- | --------------------------------------- |
| ≥1181px    | 四栏：导航 / 稿件 / 问题 / 依据         |
| 901–1180px | 三栏 + 依据收为底部抽屉，选中问题即展开 |
| ≤900px     | 单栏 + 底部标签页（稿件 / 问题 / 依据） |
