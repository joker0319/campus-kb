# Motion & Token 参考手册

SKILL.md 的配套细节数据。实现 A 类页面时按此取值。

## 缓动值表

| 用途 | 曲线 | 说明 |
|---|---|---|
| 入场/面板落位 | `cubic-bezier(.16,1,.3,1)` | expo-out，视觉主缓动 |
| 文字遮罩展开 | `cubic-bezier(.22,1,.36,1)` | 略缓一档 |
| hover/微交互 | `cubic-bezier(.4,0,.2,1)` | 标准 material，120–200ms |
| 数字滚动 | `1 - (1-p)^3` | 纯函数缓动，p 已钳制 [0,1] |

## 入场时间表模板（A 类页面）

总时长预算 ≤1.8s。顺序原则：**主视觉先动，周边内容补齐**。

```
0ms      主视觉面板        panel-settle    820ms   opacity+translateY(12px)+scale(.988)+clip
40ms     次面板 A          panel-settle    660ms
140ms    次面板 B          panel-settle    740ms
200ms    次面板 C          panel-settle    740ms
280ms    底部条            panel-settle    680ms
200ms    主标题逐字        type-unmask     780ms   每字 delay +34ms
480ms    副标题            content-rise    540ms
420ms    面板内元素         interface-settle 840ms 起错开 80ms
720ms    统计数字滚动       count-up        900ms   钳制 p
```

关键帧参考：

```css
/* 隐藏态只挂在运行态 class 下；默认样式可见 */
html.entrance-run .panel { animation: panel-settle .82s cubic-bezier(.16,1,.3,1) both; }
@keyframes panel-settle {
  from { opacity: 0; transform: translateY(12px) scale(.988); }
  62%  { opacity: 1; }
  to   { opacity: 1; transform: none; }
}
@keyframes ch-in { from { opacity:0; transform: translateY(16px) rotate(4deg); filter: blur(4px);} to {opacity:1; transform:none; filter:none;} }

@media (prefers-reduced-motion: reduce) {
  html.entrance-run .panel, html.entrance-run .ch { animation: none; opacity: 1; transform: none; filter: none; }
}
```

结束收尾：`setTimeout(() => html.classList.remove('entrance-run'), 总时长+缓冲)`。

## 逐字拆分

- 标题文字拆成 `<span class="ch">`，每字 `animation-delay: base + i*34ms`
- **在 span 上做动画，渐变色放在父级**（span 上 inline-block 会截断 background 渐变）
- 字符数超过 ~40 的标题慎用逐字（编排预算爆炸），改整块 type-unmask

## Spotlight 跟随

```css
.card { position: relative; }
.card::before {
  content: ''; position: absolute; inset: 0; pointer-events: none;
  background: radial-gradient(320px circle at var(--mx,50%) var(--my,50%),
              color-mix(in srgb, var(--accent) 8%, transparent), transparent 70%);
  opacity: 0; transition: opacity .2s;
}
.card:hover::before { opacity: 1; }
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

## 氛围层配方

```css
.bg { position: fixed; inset: 0; z-index: -1; }
.bg-aurora {  /* 两块缓移色块，20s 循环 */
  background:
    radial-gradient(40% 30% at 15% 20%, color-mix(in srgb, var(--accent) 10%, transparent), transparent),
    radial-gradient(35% 30% at 85% 60%, color-mix(in srgb, var(--accent2) 8%, transparent), transparent);
  animation: drift 20s ease-in-out infinite alternate;
}
.bg-grid {   /* 顶部渐隐网格 */
  background-image: linear-gradient(var(--line) 1px, transparent 1px),
                    linear-gradient(90deg, var(--line) 1px, transparent 1px);
  background-size: 48px 48px;
  mask-image: linear-gradient(#000 0%, transparent 55%);
}
.bg-noise {  /* SVG 噪点，opacity ≤ .04 */
  background-image: url("data:image/svg+xml,..."); opacity: .035;
}
@media (prefers-reduced-motion: reduce) { .bg-aurora { animation: none; } }
```

## Ring 描边（代替 border）

```css
.chip { box-shadow: 0 0 0 3px rgba(0,0,0,.047); }  /* 不占布局宽度 */
```

## 主题切换

```css
:root { --paper:#f7f6f2; --ink:#191714; /* … */ }
html[data-theme='dark'] { --paper:#12110f; --ink:#ece9e4; /* … */ }
```

- 初始化脚本内联在 `<head>` 读 localStorage，避免闪白
- 明暗两套都要人工过一遍对比度（正文 ≥4.5:1，大标题 ≥3:1）
