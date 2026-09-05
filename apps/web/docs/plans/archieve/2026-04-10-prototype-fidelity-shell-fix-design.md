# 原型保真度修复计划 v2 — Shell-first 精确对齐

> **日期**：2026-04-10
> **策略**：Top-Down Shell-first + 只修复已有页面
> **目标页面**：Home, Markets, Research, Trading, Platform
> **基于**：Chrome DevTools 实测对比（Playwright 提取 computed styles）

---

## 实测发现的关键问题

### P0 — 结构性断裂

| # | 问题 | 实测值 | 原型目标 |
|---|------|--------|---------|
| P0-1 | Shell Grid 不分页类型 | 所有页面 `2列3行` (56px\|1fr × 68px\|1fr\|24px) | Home `3列3行`, Analytical `3列4行` |
| P0-2 | NoiseLayer 未渲染 | DOM 中 count=0 | 应渲染 SVG 噪点+环境光 |
| P0-3 | Signature token 未定义 | `--color-signature-*`: UNDEFINED | brass hue 74 系列 |
| P0-4 | 数字字体错误 | `Inter` (sans-serif) | `JetBrains Mono` (monospace) |

### P1 — 视觉品质差距

| # | 问题 | 说明 |
|---|------|------|
| P1-1 | Header 标题缺失 | children 只有 spacer+actions，无 title |
| P1-2 | Pulse Strip 非独立行 | 嵌在 content 子 grid 内，不横跨 sidebar |
| P1-3 | Markets table layout | `auto` 而非 `fixed` |
| P1-4 | Decision Banner 不可检测 | class name 可能不匹配 |
| P1-5 | 品牌签名线用错 token | 用 accent 而非 signature(brass) |
| P1-6 | Pulse strip 无品牌光晕 | 缺 `box-shadow` + `color-mix(accent 8%, border)` |
| P1-7 | Decision banner 无品牌左边框 | 缺 `border-left: 2px solid color-mix(accent 35%)` |

### ✅ 已正确对齐

- Surface/Border/Market 色值精确匹配
- Header 磨砂玻璃 blur(12px) + 80% opacity ✅
- Panel 背景/border/radius ✅
- Rail 宽度/样式 ✅
- Body 字体 Inter 13px ✅
- Research/Trading table-layout: fixed ✅
- Status Bar 高度 24px ✅

---

## Phase 1: Token & 基础修复（所有后续工作的前提）

### 1.1 补全 Signature Token

**文件**：`src/styles/tokens/02-semantic.css`

添加 brass signature token（hue 74, warm gold）：
```css
--color-signature-300: oklch(0.680 0.045 74);
--color-signature-400: oklch(0.720 0.050 74);
--color-signature-500: oklch(0.760 0.055 74);
```

参考原型 `tokens-semantic.css` 中的 `--brand-signature-fg/muted/line/subtle`。

### 1.2 修复 font-data 字体族

**文件**：`src/styles/globals.css`

`.font-data` class 必须包含 `font-family: 'JetBrains Mono', monospace`：
```css
.font-data {
  font-family: var(--font-family-data), monospace;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
}
```

确认 `--font-family-data` 在 primitives 中定义为 `'JetBrains Mono', monospace`。

### 1.3 修复 Markets 页 DataTable layout

**文件**：使用 DataTable 组件的 Markets 页面表格

确保 `table-layout: fixed` 被正确应用。

### 1.4 验证

- `bun run check` 通过
- `--color-signature-*` 在浏览器中正确解析
- `.font-data` 元素使用 JetBrains Mono

---

## Phase 2: Shell Grid 动态化

### 2.1 AppShell grid 参数化

**文件**：`src/features/shell/components/app-shell.tsx`

当前 AppShell 使用硬编码 grid：
```tsx
grid-cols-[var(--width-rail)_1fr]
grid-rows-[var(--height-header)_1fr_var(--height-status-bar)]
```

改造为：从路由 `handle` 读取 layout 配置，动态生成 grid-template：

```tsx
interface LayoutConfig {
  columns: string;
  rows: string;
  areas: string;
}

// Home (CommandCenter)
{ columns: 'var(--width-rail) 1fr var(--width-sidebar)',
  rows: 'var(--height-header) auto 1fr',
  areas: '"rail header header" "rail pulse pulse" "rail main sidebar"' }

// Analytical (Markets/Research/Trading)
{ columns: 'var(--width-rail) 1fr var(--width-activity)',
  rows: 'var(--height-header) auto 1fr var(--height-analysis-band)',
  areas: '"rail header header" "rail strip strip" "rail main activity" "rail analysis activity"' }
```

### 2.2 布局注册

**文件**：各路由文件（`src/routes/*.tsx`）

在路由 `handle` 中添加 layout 配置：
```tsx
handle: { title: 'Home', layout: 'command-center' }
```

AppShell 内部维护 layout config 映射表。

### 2.3 删除内部 Layout 包装组件

当前 CommandCenterLayout / AnalyticalLayout 等在 content 内部创建子 grid。
改造后这些组件不再需要，因为 shell grid 已提供区域划分。

各页面组件直接接收 grid-area 命名 slot。

### 2.4 Pulse Strip 提升到 Shell 级

**文件**：Home 页面

PulseSection 从 content 子 grid 提升到 shell grid 的 `pulse` area。
这样它横跨 main + sidebar 全宽。

### 2.5 验证

- Home 页 3 列 3 行 grid（rail|header|header / rail|pulse|pulse / rail|main|sidebar）
- Analytical 页 3 列 4 行 grid
- Pulse strip 横跨全宽
- `bun run check` 通过

---

## Phase 3: NoiseLayer 修复 + 材质感层

### 3.1 NoiseLayer 渲染修复

**文件**：`src/features/shell/components/noise-layer.tsx`

调查为什么 NoiseLayer 没有渲染到 DOM 中。可能原因：
- SVG filter ID 不匹配
- opacity 太低导致不可见
- absolute 定位问题

### 3.2 Header 签名线修复

**文件**：`src/features/shell/components/header.tsx`

将 header `::after` 的颜色从 `accent 25%` 改为 `signature-line`：
```css
background: linear-gradient(90deg,
  transparent 0%,
  color-mix(in oklch, var(--color-signature-400) 15%, transparent) 20%,
  color-mix(in oklch, var(--color-signature-400) 25%, transparent) 50%,
  color-mix(in oklch, var(--color-signature-400) 15%, transparent) 80%,
  transparent 100%);
```

### 3.3 添加标题品牌下划线

**文件**：`src/features/shell/components/header.tsx`

在标题元素上添加 `::after`：
```css
content: '';
position: absolute;
bottom: -4px;
left: 0;
width: 40%;
height: 2px;
background: linear-gradient(90deg, var(--color-accent) 30%, var(--color-signature-400) 60%, transparent 100%);
border-radius: 1px;
```

### 3.4 Pulse Strip 品牌光晕

**文件**：PulseSection / 各 strip 组件

添加：
```css
border-bottom: 1px solid color-mix(in oklch, var(--color-accent) 8%, var(--color-border-subtle));
box-shadow: 0 1px 4px -1px color-mix(in oklch, var(--color-accent) 6%, transparent);
```

### 3.5 Decision Banner 品牌左边框

**文件**：DecisionBanner 组件

添加：
```css
border-left: 2px solid color-mix(in oklch, var(--color-accent) 35%, transparent);
```

### 3.6 验证

- NoiseLayer SVG 噪点在所有页面可见
- Header 底部签名线为 warm brass 色调
- 标题下方有品牌下划线
- Pulse strip 有微弱光晕
- `bun run check` 通过

---

## Phase 4: 动画 & 交互层

### 4.1 补全缺失 Keyframes

**文件**：`src/styles/globals.css`

```css
@keyframes dot-critical-pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
@keyframes value-flash { 0% { opacity: 0.85; transform: translateY(0.5px); } 100% { opacity: 1; transform: translateY(0); } }
@keyframes task-breathe { 0%, 100% { opacity: 1; } 50% { opacity: 0.88; } }
@keyframes conclusion-appear { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }
@keyframes tab-reveal { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }
```

### 4.2 Active/Pressed 微反馈

**文件**：`src/styles/globals.css`

```css
.decision-cta:active { transform: scale(0.97); transition: transform 100ms cubic-bezier(0.4, 0, 0.2, 1); }
.queue-item:active { background: var(--color-interaction-hover-strong-bg); }
```

### 4.3 Reduced Motion 支持

**文件**：`src/styles/globals.css`

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

### 4.4 Sparkline 升级 (Catmull-Rom)

**文件**：`src/components/data/sparkline/sparkline.tsx`

将 `<polyline>` 替换为 Catmull-Rom 样条曲线 `<path>`。

### 4.5 验证

- 紧急告警圆点有 dot-critical-pulse 动画
- 数值更新有 value-flash 反馈
- Sparkline 显示平滑曲线
- `prefers-reduced-motion` 生效
- `bun run check` 通过

---

## Phase 5: 逐页精修

### 5.1 Home 页

- Decision Banner: 3 栏 grid(5fr 4fr 3fr) + 品牌左边框
- Context Section: 双线分隔（border-subtle + overlay-3 ::before）
- Queue Item: 验证 hover 负 margin 展开效果
- 全部数字区域 font-data JetBrains Mono

### 5.2 Markets 页

- DataTable: `table-layout: fixed`
- Context Bar: 确保横跨全宽
- CrossMarketMatrix: 确认热力图颜色映射

### 5.3 Research 页

- FactorTable: 10 列完整渲染
- Analysis Band: 4 tab 面板
- IC/IR 条件格式色阶

### 5.4 Trading 页

- Decision Banner: 独立 grid area
- Positions Table: 8 列 + 行底色
- Orders Panel: 3 tab 完整
- Signal Queue: 优先级条渐变

### 5.5 Platform 页

- Ops Console layout
- Health strip + detail panel

### 5.6 全局验证

- `bun run check` 通过
- 逐页截图对比原型
- 覆盖率 ≥ 80%

---

## 执行策略

| Phase | 依赖 | 预估复杂度 | 涉及文件数 |
|-------|------|-----------|-----------|
| P1 Token 基础 | 无 | 低 | ~3 |
| P2 Shell Grid | P1 | 中高 | ~15 |
| P3 材质感层 | P2 | 中 | ~6 |
| P4 动画交互 | P2 | 中 | ~4 |
| P5 逐页精修 | P3+P4 | 高 | ~15 |

**执行顺序**：P1 → P2 → P3+P4 并行 → P5
