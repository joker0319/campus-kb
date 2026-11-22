# Motion & Token 参考手册

SKILL.md 的配套细节数据。实现 A 类页面时按此取值；B 类页面只用「B 类落位」一条。

## 缓动值表（以 tokens.css 为准）

| 用途 | 曲线 | 说明 |
|---|---|---|
| **全局主缓动** | `cubic-bezier(.22,1,.36,1)` | `var(--ease)`，入场/3D/微交互统一用它 |
| hover / 微交互 | `cubic-bezier(.4,0,.2,1)` | 标准 material，120–200ms |
| 呼吸精灵 | `ease-in-out` | 仅 PetMascot 呼吸用；幅度极小 |
| 数字滚动 | `1 - (1-p)^3` | 纯函数缓动，p 已钳制 [0,1] |

> 历史值 `cubic-bezier(.16,1,.3,1)` 已废弃，见 SKILL.md §3。

## 当前实际入场参数

```css
/* A 类首页：landing.module.css */
.page[data-run='true'] .in {
  animation: lRise .85s var(--ease) both;
  animation-delay: var(--d, 0s);          /* 每个元素独立延时 */
}
@keyframes lRise {
  from { opacity: 0; transform: translateY(14px); }
  to   { opacity: 1; transform: none; }
}

/* 全局基线：global.css */
html.motion-run .js-anim {
  opacity: 0; transform: translateY(6px);
  animation: js-rise .42s var(--ease) both;
  animation-delay: var(--d, 0s);
}
@keyframes js-rise { to { opacity:1; transform:none; } }

/* B 类工作台：一次落位，≤420ms，无循环 */
@media (prefers-reduced-motion: reduce) {
  .page[data-run='true'] .in,
  html.motion-run .js-anim { animation: none; opacity:1; transform:none; }
}
```

**收尾必须做**：动画结束后移除运行态 class（`.page` 的 `data-run`、`html` 的 `motion-run`），DOM 回到纯静态样式。不移除 = 白屏风险。

## 第一版 bento 入场时间表（仅作度量思维参照，勿照搬）

原 bento 五宫格基准画布 1374×666，总时长预算 ≤1.8s，主视觉先动：

```
0ms      主视觉面板      panel-settle    820ms   opacity + translateY(12px) + scale(.988) + clip
40ms     次面板 A        panel-settle    660ms
140ms    次面板 B        panel-settle    740ms
200ms    次面板 C        panel-settle    740ms
280ms    底部条          panel-settle    680ms
200ms    主标题逐字      type-unmask     780ms   每字 delay +34ms
480ms    副标题          content-rise    540ms
420ms    面板内元素      interface-settle 840ms 起错开 80ms
720ms    统计数字滚动    count-up        900ms   钳制 p
```
该版已被判定 AI 味重而废弃。**保留的是"先定基准与坐标、再写 CSS"的度量方法，不是密集卡片堆砌本身。**

## 逐字拆分（如确需）

- 标题拆成 `<span class="ch">`，每字 `animation-delay: base + i*34ms`
- **在 span 上做动画，渐变色放父级**（span inline-block 会截断 background 渐变）
- 字符数超过 ~40 的标题改用整块 type-unmask，避免编排预算爆炸

## 3D 卡堆（CaseStage 真实参数）

```css
.stage  { perspective: 1400px; perspective-origin: 50% 44%; }
.deck   { transform-style: preserve-3d;
          transform: rotateX(var(--rx,2deg)) rotateY(var(--ry,-7deg));
          transition: transform .55s var(--ease); }
.ghost  { transform: translate3d(0,15px,-34px) scale(.978) rotate(-1.7deg); opacity:.9; }
.ghost2 { transform: translate3d(0,30px,-66px) scale(.955) rotate(1.9deg);  opacity:.6; }
.sheet  { transform: translateZ(18px); animation: sheetIn .62s var(--ease) both; }
@keyframes sheetIn {
  from { opacity:0; transform: rotateY(10deg) translateZ(-26px); }
  to   { opacity:1; transform: rotateY(0deg) translateZ(18px); }
}
```
**规则**：`preserve-3d` 只开在 stage/deck；ghost 与 sheet 叶子节点拍平，规避 Safari 层化与 1px 缝隙。≤1020px 关掉旋转、隐藏 ghost；reduced-motion 全部停用。切换节奏 5.6s，hover 暂停。

## 墨点精灵（PetMascot 真实参数）

```css
.breathe { animation: breathe 3.8s ease-in-out infinite; }         /* scale(1.022,.975) */
.eyes    { animation: blink 4.8s var(--ease) infinite; }           /* 94% 时 scaleY(.08)，占 3% */
.pupils  { transform: translate(var(--gx,0px), var(--gy,0px));      /* 瞳孔跟随光标 */
           transition: transform .18s ease-out; }
```
原则：微动要像生物，不像定时器。呼吸幅度大一点就成蹦跳玩具，眨眼频率高一点就成癫痫。

## Spotlight 跟随（备用，当前未在主页启用）

```css
.card { position: relative; }
.card::before {
  content:''; position:absolute; inset:0; pointer-events:none;
  background: radial-gradient(320px circle at var(--mx,50%) var(--my,50%),
              color-mix(in srgb, var(--brand) 8%, transparent), transparent 70%);
  opacity:0; transition: opacity .2s;
}
.card:hover::before { opacity:1; }
```
```ts
el.addEventListener('mousemove', e => {
  const r = el.getBoundingClientRect();
  el.style.setProperty('--mx', `${e.clientX - r.left}px`);
  el.style.setProperty('--my', `${e.clientY - r.top}px`);
});
```

## 数字滚动（防负数版）

```ts
function countUp(el: HTMLElement, target: number, dur = 900) {
  let start: number | null = null;
  const tick = (now: number) => {
    if (start === null) start = now;
    const p = Math.min(Math.max((now - start) / dur, 0), 1); // 必须钳制
    el.textContent = String(Math.round(target * (1 - Math.pow(1 - p, 3))));
    if (p < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}
```

## 氛围层配方（当前 landing.module.css 实值）

```css
.bg { position:fixed; inset:0; z-index:-1; pointer-events:none; }
.bgAurora {
  background:
    radial-gradient(42% 32% at 14% 18%, color-mix(in srgb, var(--brand) 9%, transparent), transparent),
    radial-gradient(38% 30% at 86% 64%, color-mix(in srgb, var(--ok) 7%, transparent), transparent);
  animation: drift 22s var(--ease) infinite alternate;
}
.bgGrid {
  background-image: linear-gradient(var(--line-2) 1px, transparent 1px),
                    linear-gradient(90deg, var(--line-2) 1px, transparent 1px);
  background-size: 48px 48px;
  mask-image: linear-gradient(#000 0%, transparent 52%);
}
.bgNoise { opacity:.035; background-image: url("data:image/svg+xml,%3Csvg ... feTurbulence ..."); }
```
三层叠加透明度总和不得让前景文字对比度掉到 4.5:1 以下。

## Ring 描边（代替 border）

```css
.ctaGhost { box-shadow: 0 0 0 3px rgba(0,0,0,.047); }  /* 不占布局宽度 */
```

## 主题切换（备用，当前未启用）

```css
:root { --paper:#fcfbf8; --ink:#191917; /* … */ }
html[data-theme='dark'] { --paper:#12110f; --ink:#ece9e4; /* … */ }
```
- 初始化脚本内联在 `<head>` 读 localStorage，避免闪白
- 明暗两套都过对比度（正文 ≥4.5:1，大标题 ≥3:1）
