# 校稿台 · 前端

媒体传讯处通讯员工作包的前端（「校稿台」设计的 React + TS 实现）。

## 运行

```bash
npm install
npm run dev        # http://127.0.0.1:5173
npm run build      # 类型检查 + 生产构建 → dist/
npm test           # 55 个用例（含真实接口夹具测试）
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
  App.tsx               hash 路由：#/ 首页 · #/desk 校稿台 · #/assistant 助手
  pages/Landing.tsx     首页（导航 + 主体 + 底部，动效编排）
  pages/Desk.tsx        校稿台（克制模式）
  pages/Assistant.tsx   助手页界面壳（能力待接入，输入禁用）
  types.ts              领域模型（Issue 用 `${ruleId}@${line}` 作稳定 key）
  data/content.ts       送审稿件与规则出处（依据栏）；命中不再内置
  lib/review.ts         纯函数：筛选、计数、键盘导航、标记严重度
  lib/api.ts            POST /api/review：finding → Issue 映射、严重度收敛
  lib/segments.ts       按命中词切分正文（split + 捕获组，比 replace 安全）
  lib/buildDraft.ts     任意正文 + 后端精确 hit → 带 issueKeys 的 Draft（动态标红）
  lib/countUp.ts        数字滚动（进度钳制，防 rAF 负时间差）
  hooks/useReview.ts    useReducer 状态机（选中/筛选/忽略/导航）
  hooks/useReviewRequest.ts  校验请求：loading/ready/error + 重试/取消 + 换稿送审
  hooks/useMediaQuery.ts
  components/           Shell(AppBar/Rail/StatusBar/Tabs)、DocumentPane、IssueList、EvidencePane
                        PetMascot（墨点 → 助手入口）、CorpusSearch（档案检索抽屉）
                        SubmitDialog（粘贴稿件弹窗）
  styles/tokens.css     设计 token 唯一来源
  styles/*.module.css   各页样式
```

## 与后端的接口

校稿台启动即 `POST /api/review`（正文来自 `DRAFT_TEXT`），命中经 `lib/api.ts` 映射为 `Issue[]`；
后端 key `ruleId@line` 与正文片段标注直接对齐，组件层不用改。
顶栏「粘贴稿件」可送审任意正文：后端每条 finding 返回精确命中子串 `hit`，前端 `lib/buildDraft.ts`
按行号与 `hit` 切分正文、挂上 `issueKeys`，因此新稿件也能逐处标红并点回依据，不依赖内置样例。
Vite 开发代理把 `/api` 转发到 `127.0.0.1:8000`（FastAPI）。
左栏「资源」打开档案检索抽屉，调 `GET /api/search`。
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
