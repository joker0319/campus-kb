# 校稿台 · 前端

媒体传讯处通讯员工作包的前端（第三版「校稿台」设计的 React + TS 实现）。

## 运行

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # 类型检查 + 生产构建 → dist/
npm test           # 39 个用例：纯函数 21 + 组件交互 18
npm run lint       # ESLint（含类型感知规则）
npm run format     # Prettier 格式化
npm run check      # 类型 + lint + 格式 + 测试，提交前跑这个
```

## 代码规范

- **ESLint 10**（flat config）：`typescript-eslint` 的 `recommendedTypeChecked`，
  开类型感知，能抓 `no-floating-promises` 这类纯语法规则抓不到的问题；
  外加 `react-hooks` v7（含 React Compiler 时代的 `set-state-in-effect` 等规则）。
- **Prettier 3**：`printWidth 100`、单引号、尾逗号。格式规则全部交给 Prettier，
  由 `eslint-config-prettier` 关掉 ESLint 里冲突的部分，两者不打架。
- 编辑器已配好：`.vscode/settings.json` 保存时自动格式化 + 自动修 ESLint 可修项。
  首次打开装两个推荐扩展即可（ESLint、Prettier）。
- 新增规则改 `eslint.config.js`；`vite.config.ts`、`*.config.js` 不在业务 tsconfig 内，
  已单独关掉类型感知规则，避免解析报错。

## 结构

```
src/
  App.tsx               hash 路由：#/ 首页 · #/desk 校稿台
  pages/Landing.tsx     首页（A 类页面，全套动效编排）
  pages/Desk.tsx        校稿台（B 类页面，克制模式）
  types.ts              领域模型（Issue 用 `${ruleId}@${line}` 作稳定 key）
  data/content.ts       稿件 / 17 条命中 / 13 条规则定义，全部来自 campus-kb 实测
  lib/review.ts         纯函数：筛选、计数、键盘导航、标记严重度
  lib/segments.ts       按命中词切分正文（split + 捕获组，比 replace 安全）
  lib/countUp.ts        数字滚动（进度钳制，防 rAF 负时间差）
  hooks/useReview.ts    useReducer 状态机
  hooks/useMediaQuery.ts
  components/           Shell(AppBar/Rail/StatusBar/Tabs)、DocumentPane、IssueList、EvidencePane
                        CaseStage（首页 3D 稿件卡轮播）、PetMascot（墨点小助手）
  styles/tokens.css     设计 token 唯一来源
  styles/landing.module.css
  styles/desk.module.css
  styles/case.module.css
  styles/pet.module.css
```

## 接入后端时要改的地方

只有 `data/content.ts`：把常量换成 `GET /api/drafts/:id/review` 的响应，字段对应
`Issue[]` / `Paragraph[]` / `Rule[]`，组件层与状态机不用动。

## 刻意的取舍

- **CSS Modules 而非 Tailwind**：设计值是精调的 px（15px 正文、1.95 行高、2px 校样下划线），
  塞进 Tailwind 会变成一堆 arbitrary value，改一处要翻三处。
- **字体全部系统栈**：内网无法访问 Google Fonts，外链字体一旦 fallback，度量全部失配。
- **正文不随视口缩放**：工作台不是落地页，13 寸与 27 寸上正文都必须是 15px。
- **入场动画的隐藏起始态只挂在 `html.motion-run` 下**：若写进默认样式，动画结束移除 class 后
  元素会回落到隐藏态（整页白屏）。`index.html` 在首帧前打标记，`App` 在 900ms 后摘除。

## 响应式

| 宽度       | 布局                                    |
| ---------- | --------------------------------------- |
| ≥1181px    | 四栏：导航 / 稿件 / 问题 / 依据         |
| 901–1180px | 三栏 + 依据收为底部抽屉，选中问题即展开 |
| ≤900px     | 单栏 + 底部标签页（稿件 / 问题 / 依据） |
