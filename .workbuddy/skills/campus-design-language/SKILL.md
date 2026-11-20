---
name: campus-design-language
description: 校园资源库/校稿台项目（campus-portal）的前端设计语言规范。提炼自 motionsites、aceternity、showreel、uiverse、reactbits、animejs 六个参考站，并加入本项目的工程约束与"去 AI 味"原则。当为本项目开发任何新页面、新组件、新动效，或用户要求视觉升级/设计评审时必须加载本 skill；尤其适用于首页/落地页、宣传页、以及工作台界面的视觉决策。
agent_created: true
---

# Campus Design Language

campus-portal 项目的设计语言规范。核心立场：**设计语言是分层的——首页负责气质，工作台负责效率**。同一套原理，两套强度。

## 双模式路由（先判断页面类型再动手）

| 页面类型 | 例子 | 动效强度 | 参照 |
|---|---|---|---|
| **A 首页/落地页** | `Landing`、宣传页、关于页 | 全套：逐字入场、spotlight、噪点、aurora、数字滚动 | motionsites / aceternity / showreel |
| **B 工作台/工具页** | 校稿台 `Desk`、列表页、表单页 | 仅一次 ≤420ms 分层落位；无渐变、无光斑、无逐字动画 | Linear / Notion 的克制 |

误判代价：在 B 类页面套 A 类语言 = 用户评价"AI 味重"；在 A 类页面套 B 类 = 平淡无记忆点。动手前先确认类型。

## 六个参考站的共同语言（A 类页面使用）

1. **编辑感排版**：特大标题（clamp 3~7rem）、字距收紧（-0.02em~-0.035em）、行高 1.1~1.2；中文可用衬线（宋体/霞鹜文楷）营造编辑感，正文保持黑体
2. **一次性入场编排**：每个元素独立 duration + delay 的 staggered 时间表，全站动效只演一次；禁"所有元素同时淡入"
3. **氛围层**：aurora 缓移色块 + 顶部渐隐网格 + 细噪点（SVG feTurbulence 或 base64），三者叠加但透明度总和不超过 0.5，不得干扰前景文字对比度
4. **Bento 网格**：不等权卡片 + 数字滚动 + ring 描边（`box-shadow: 0 0 0 3px rgba(0,0,0,.047)` 代替 border，不占布局宽度）
5. **微交互**：按钮磁吸（translate 随光标偏移 ≤6px）、卡片 spotlight 跟随（radial-gradient 随 mousemove 更新 CSS 变量）、hover 上浮 1~2px
6. **缓动统一**：所有入场用 `cubic-bezier(.16,1,.3,1)`（expo-out）；禁 ease-in-out 全场通吃

## 硬性约束（违反即返工）

### 零外部资源
- **禁止外部资源**：无 Google Fonts、无 CDN 图片、无 Lottie。字体一律系统栈
- 中文系统栈基准：`-apple-system, "PingFang SC", "Microsoft YaHei", sans-serif`；衬线：`"Songti SC", "SimSun", serif`
- 外链字体一旦 fallback，所有基于字宽的度量（入场编排、clip-path 遮罩）全部失配

### 动画安全（白屏教训，必须遵守）
- 元素默认样式**必须可见**；隐藏初始态只允许挂在 `html.entrance-run` 这类"运行态"选择器下
- 入场标记脚本放 `<head>`（或组件首帧 effect）在渲染前执行；动画结束后**移除运行态 class**，DOM 回到纯静态样式
- 倒计时驱动数字滚动时，进度 `p` 必须钳制 `Math.min(Math.max(p,0),1)`——rAF 时间戳可能早于 performance.now()，会产生负数
- `prefers-reduced-motion: reduce` 用户直接跳过全部动效，元素立即可见
- 必须用无头浏览器同时验证「动画结束后」状态（移除运行态 class 后截图），仅验证静态化版本会漏掉此类 bug

### 去 AI 味（反模式清单）
以下任何一项出现，即视为不合格：
- ❌ 紫粉/蓝紫渐变 + 玻璃拟态卡片堆砌（2023 后 AI 生成页的指纹配色）
- ❌ 所有元素同时在动、永远在动的循环动画堆满一屏
- ❌ 装饰性氛围文案（"赋能""一站式""开启新体验"）——文案必须具体到数字和名词
- ❌ 无来源的数字。所有统计必须来自真实数据源（本项目：`campus-kb` 校验结果、规则库）
- ❌ clip-path 遮罩动画叠加 border-radius 时未处理 Safari 白边

**克制的本质是具体性**：真实的规则编号、真实的命中统计、真实的矛盾（如手册中英文排名不一致），比任何渐变更能建立可信度。

### B 类页面附加规则
- 正文固定 15px/1.95，不随视口缩放（工作台不是落地页）
- 色彩只用中性色 + 语义色（错误红、警告黄、成功绿），品牌色只作点缀
- 交互反馈即时（≤120ms transition），不做入场编排循环

## 实现速查

- 设计 token 统一放 `src/styles/tokens.css`，组件内不出现裸色值
- 样式用 CSS Modules，不用 Tailwind（设计值太具体，arbitrary value 会失控）
- 度量系统（A 类整页缩放场景）：`html { font-size: min(calc(95vw / W), calc(94vh / H)) }`，W×H 为设计稿基准；B 类页面禁用此法
- 动效时长上限：入场总时长 ≤1.8s；单元素 ≤900ms
- 主题切换（明暗）：CSS 变量双套 + `data-theme` 属性，localStorage 持久化；两套都需单独校验对比度

详细参数（时间表模板、缓动值表、spotlight/bento 的 CSS 片段）见 `references/motion-tokens.md`。

## 现有实现参照

- A 类：`campus-portal/prototype/v1-mosaic.html`（第一版首页原型，含完整入场编排与双主题）
- B 类：`campus-portal/web/src/components/*`（校稿台，CSS Modules + tokens.css）
- 新页面在 `campus-portal/web` 内用 React + TS + CSS Modules 实现，路由用 hash 简易切换即可，不必引入 router
