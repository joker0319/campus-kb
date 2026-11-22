---
name: campus-design-language
description: 校园知识库/校稿台项目（campus-portal）的前端设计语言规范。提炼自用户提供的 motionsites、aceternity、showreel、uiverse、reactbits、animejs 六个参考站及一份 bento 五宫格像素级复刻 prompt，并落到本项目当前的纸墨 token 体系与"去 AI 味"原则上。当为本项目开发任何新页面、新组件、新动效，或做视觉升级/设计评审时必须加载；尤其适用于首页、助手页、校稿台、3D 轮播与墨点入口的视觉决策。
agent_created: true
---

# Campus Design Language

campus-portal 的设计语言规范。核心立场：**设计语言是分层的——首页负责气质，工作台负责效率**。同一套原理，两套强度。

> 本文件自包含，读完即可动手。细节数据表见 `references/`。

## 1. 双模式路由（先判断页面类型再动手）

| 页面类型 | 当前对应文件 | 动效强度 | 参照 |
|---|---|---|---|
| **A 首页/落地页** | `pages/Landing.tsx`、`CaseStage.tsx`、`PetMascot.tsx` | 氛围层 + 一次性入场 + 3D 轮播 + 精灵微动 | motionsites / aceternity / showreel / reactbits |
| **B 工作台/工具页** | `pages/Desk.tsx`、`pages/Assistant.tsx`、`components/*Dialog` | 仅一次 ≤420ms 分层落位；无渐变、无光斑、无逐字动画 | Linear / Notion 的克制 |

**误判代价**：在 B 类页面套 A 类语言 = 用户评价"AI 味重"（历史上反复出现）；在 A 类页面套 B 类 = 平淡无记忆点。动手前先确认类型。

## 2. 六个参考站各自贡献了什么

用户提供的六个站不是让你抄模板，而是各自提供一个语汇。当前项目**只取用标注「在用」的部分**：

| 站点 | 借鉴的语汇 | 本项目状态 |
|---|---|---|
| **motionsites** | 一次性 staggered 入场编排、滚动驱动叙事 | ✅ 在用（首页 `.in` + `--d` 延时） |
| **aceternity** | aurora 氛围层、spotlight/bento 卡片、ring 描边 | ✅ 在用（`.bgAurora` / `.bgGrid` / `.bgNoise` / ring 描边） |
| **showreel** | 编辑感特大衬线标题、字距收紧、大片留白 | ✅ 在用（`.title` clamp 2.9~4.6rem / -0.035em） |
| **uiverse** | 有生命感的微交互小组件（呼吸 / 眨眼 / 跟随） | ✅ 在用（墨点精灵 PetMascot） |
| **reactbits** | 纯 CSS 3D 卡片堆、透视与层叠 | ✅ 在用（CaseStage 3D 卡堆，不用 three.js） |
| **animejs** | 缓动统一、时间表思维、reduced-motion 降级 | ✅ 在用（统一 `--ease`，全站降级） |

**一份 bento 五宫格像素级复刻 prompt**（度量基准 1374×666，五卡精确坐标/渐变/SVG/入场时间表）曾用于第一版原型 `prototype/v1-mosaic.html`。它确立的**度量系统思维**（先定基准画布与坐标，再写 CSS）保留了；但那版密集 bento 被用户判定"AI 味重、节目奇怪"，已废弃。**不要照搬那套卡片堆砌**——它是反面教材。详尽参数见 `references/motion-tokens.md`。

## 3. 当前 token 体系（唯一来源 `src/styles/tokens.css`）

组件**只引用变量，不写字面颜色**。新增颜色必须先加 token。

```css
/* 纸与墨 —— 全局底色是暖白，不是纯白 */
--paper: #fcfbf8;   --surface: #ffffff;  --sunk: #f7f6f1;
--ink:  #191917;    --ink-2: #54514a;    --ink-3: #8b877c;  --ink-4: #a9a49a;
--line: #e6e3da;    --line-2: #efede6;

/* 语义色 —— 三个校样状态 + 品牌点缀，不引入装饰色 */
--err: #a32b24;  --err-tint: rgba(163,43,36,.085);
--warn: #8a6a1f; --warn-tint: rgba(138,106,31,.1);
--ok: #4a6b4a;
--brand: #8c1d2f; --brand-tint: rgba(140,29,47,.055);
--mark-on: #f4f1ea; --mark-on-line: #e1dcd0;

/* 字体栈 —— 系统字体，零外部资源 */
--sans:  'PingFang SC','HarmonyOS Sans SC','Hiragino Sans GB','Microsoft YaHei',system-ui,-apple-system,sans-serif;
--serif: 'Songti SC','Noto Serif SC','Source Han Serif SC',Georgia,serif;
--mono:  'SF Mono',ui-monospace,Menlo,Consolas,monospace;

/* 唯一主缓动 —— 不要另起 expo-out 曲线 */
--ease: cubic-bezier(.22,1,.36,1);
```

**注意**：历史文档曾写 `cubic-bezier(.16,1,.3,1)`（expo-out），那是过时值。以 `tokens.css` 的 `.22,1,.36,1` 为准，全站统一。

## 4. 当前页面实现速查（改这些文件前先读）

| 组件 | 关键实现参数 |
|---|---|
| **首页入场** | `landing.module.css`：`.page[data-run='true'] .in` → `lRise .85s`，`translateY(14px)`，delay 走 `--d`；**动画结束移除 `data-run`** |
| **全局入场** | `global.css`：`html.motion-run .js-anim` → `js-rise .42s`，`translateY(6px)` |
| **3D 轮播** | `case.module.css`：`perspective:1400px`，deck `rotateX(2deg) rotateY(-7deg)`，两层 ghost 稿 `translateZ(-34/-66px)`，正文 `translateZ(18px)`；hover 暂停、5.6s 自动切；`preserve-3d` **只开在 stage/deck，叶子拍平** |
| **墨点入口** | `pet.module.css`：呼吸 3.8s `scale(1.022,.975)`、眨眼 4.8s（94% 时 `scaleY(.08)`）、瞳孔 `translate(var(--gx),var(--gy))` 跟随；幅度必须极小，大了就成了蹦跳玩具 |
| **氛围层** | `landing.module.css`：aurora 双径向渐变（品牌色 9% / 成功色 7%，22s 缓移）+ 48px 渐隐网格 + SVG feTurbulence 噪点 opacity .035；`z-index:-1` 且 `pointer-events:none` |

## 5. 硬性约束（违反即返工）

### 零外部资源
- 无 Google Fonts、无 CDN 图片、无 Lottie。字体一律系统栈
- 外链字体一旦 fallback，所有基于字宽的度量（入场编排、clip-path 遮罩）全部失配

### 动画安全（白屏教训，必须遵守）
- 元素默认样式**必须可见**；隐藏起始态只允许挂在 `data-run='true'` / `html.motion-run` 这类"运行态"选择器下
- 入场标记脚本放 `<head>`（或组件首帧 effect）在渲染前执行；动画结束后**移除运行态 class**，DOM 回到纯静态样式
- 数字滚动进度 `p` 必须钳制 `Math.min(Math.max(p,0),1)`——rAF 时间戳可能早于 `performance.now()`，会产生负数
- `prefers-reduced-motion: reduce` 用户直接跳过全部动效，元素立即可见
- 必须用无头浏览器验证「动画结束后」状态，仅验证静态版会漏掉白屏 bug
- 3D：`preserve-3d` 只开在容器，叶子节点拍平，规避 Safari 层化与 1px 缝隙

### 去 AI 味（反模式清单）
以下任何一项出现，即视为不合格：
- ❌ 紫粉/蓝紫渐变 + 玻璃拟态卡片堆砌（AI 生成页的指纹配色）——本项目品牌色是**深红 `#8c1d2f`**，不是紫
- ❌ 密集 bento 五宫格堆砌（第一版原型的教训）
- ❌ 所有元素同时在动、永远在动的循环动画堆满一屏
- ❌ 装饰性氛围文案（"赋能""一站式""开启新体验"）——文案必须具体到数字和名词
- ❌ 无来源的数字。所有统计必须来自真实数据源（`campus-kb` 校验结果、规则库、档案库）
- ❌ clip-path 遮罩叠加 border-radius 时未处理 Safari 白边

**克制的本质是具体性**：真实的规则编号、真实的命中统计、真实的矛盾（如手册中英文排名不一致），比任何渐变更能建立可信度。

### B 类页面附加规则
- 正文固定约 13~15px / 1.9，不随视口缩放（工作台不是落地页）
- 色彩只用中性色 + 语义色（错误红、警告黄、成功绿），品牌色只作点缀
- 交互反馈即时（≤150ms transition），不做入场编排循环
- 样式用 **CSS Modules**，不用 Tailwind（设计值太具体，arbitrary value 会失控）

## 6. 工程约束

- 新页面在 `campus-portal/web` 内用 React + TS + CSS Modules 实现；hash 路由 `#/`、`#/desk`、`#/assistant` 简易切换，不引入 router
- token 统一放 `src/styles/tokens.css`，组件内不出现裸色值
- 主题若需明暗切换：CSS 变量双套 + `data-theme` 属性，localStorage 持久化，两套都单独校验对比度
- A 类整页缩放场景度量：`html { font-size: min(calc(95vw / W), calc(94vh / H)) }`（W×H 为设计稿基准，如 1374×666）；**B 类禁用此法**

## 7. 参照文件

- token 唯一来源：`campus-portal/web/src/styles/tokens.css`
- 全局基线与入场：`campus-portal/web/src/styles/global.css`
- A 类样板：`landing.module.css` + `case.module.css` + `pet.module.css`
- B 类样板：`desk.module.css` + `assistant.module.css` + `dialog.module.css`
- 废弃原型（仅作反面参照）：`campus-portal/prototype/v1-mosaic.html`
- 细节数据与时间表：`references/motion-tokens.md`；参考站与 bento prompt 溯源：`references/reference-sites.md`
