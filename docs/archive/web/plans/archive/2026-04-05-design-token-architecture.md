# Design Token Architecture — CSS 唯一真源方案

> **状态**：已完成
> **日期**：2026-04-05
> **完成日期**：2026-04-05
> **决策依据**：业界调研 + 项目约束

---

## 1. 核心决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 唯一真源格式 | CSS | 纯 Web 项目 + Tailwind v4 CSS-first + shadcn/ui 生态约定 |
| 文件拆分 | 按层（9 层） | 与原型一一对应，依赖链清晰，迁移简单 |
| @theme 模式 | 分散式 | 每个 token 文件自包含 `@theme inline {}`，Tailwind 自动合并 |
| 命名空间 | Tailwind 原生映射 | 所有颜色 `--color-` 前缀，直接生成 `bg-xxx` / `text-xxx` |
| 命名风格 | shadcn 模式 | token 名描述「是什么」，工具类描述「用在哪」 |

## 2. 目录结构

```
src/styles/
  tokens/
    01-primitives.css      # L1 原语：色板、间距、圆角、动效
    02-semantic.css        # L2 语义表面：surface / foreground / border
    03-shell.css           # L3 Shell 布局尺寸
    04-data-viz.css        # L4 数据可视化
    05-component.css       # L5 组件结构
    06-interaction.css     # L6 交互反馈状态
    07-domain.css          # L7 业务域（市场/风控/交易/AI 等）
    08-density.css         # L8 密度预设（compact / comfortable / dense）
  themes/
    dark.css               # 暗色主题覆盖（默认）
    light.css              # 亮色主题覆盖
    market-intl.css        # 国际市场色覆盖
  fonts.css               # 字体声明
  globals.css             # 入口：@import "tailwindcss" + @import 全部
```

## 3. globals.css 入口

```css
@import "tailwindcss";

/* Token layers — 按依赖顺序 */
@import "./tokens/01-primitives.css";
@import "./tokens/02-semantic.css";
@import "./tokens/03-shell.css";
@import "./tokens/04-data-viz.css";
@import "./tokens/05-component.css";
@import "./tokens/06-interaction.css";
@import "./tokens/07-domain.css";
@import "./tokens/08-density.css";

/* Theme overrides — 最后加载 */
@import "./themes/dark.css";
@import "./themes/light.css";
@import "./themes/market-intl.css";
```

## 4. 各层 Token 规范

### 4.1 L1 Primitives（原语）

**原则**：无语义，只定义「设计选项」。

```css
/* 01-primitives.css */
@theme inline {
  /* 中性色板 — 蓝调灰 (hue 254) */
  --color-neutral-0:   oklch(99%  0.002 254);
  --color-neutral-50:  oklch(97%  0.005 254);
  --color-neutral-100: oklch(93%  0.007 254);
  --color-neutral-200: oklch(86%  0.009 254);
  --color-neutral-300: oklch(74%  0.011 254);
  --color-neutral-400: oklch(58%  0.012 254);
  --color-neutral-500: oklch(46%  0.012 254);
  --color-neutral-600: oklch(38%  0.011 254);
  --color-neutral-700: oklch(30%  0.010 254);
  --color-neutral-800: oklch(24%  0.009 254);
  --color-neutral-900: oklch(20%  0.008 254);
  --color-neutral-950: oklch(14%  0.006 254);

  /* 品牌色 — hue 255 */
  --color-brand-50:  oklch(95% 0.06 255);
  --color-brand-200: oklch(80% 0.10 255);
  --color-brand-500: oklch(60% 0.18 255);
  --color-brand-700: oklch(50% 0.16 255);

  /* 功能色 — 6 色相 x 3 级 */
  --color-red-400:    oklch(65% 0.20 25);
  --color-red-600:    oklch(50% 0.18 25);
  --color-green-400:  oklch(70% 0.16 155);
  --color-green-600:  oklch(55% 0.14 155);
  --color-amber-400:  oklch(75% 0.15 85);
  --color-amber-600:  oklch(60% 0.14 85);
  --color-blue-400:   oklch(65% 0.15 255);
  --color-blue-600:   oklch(50% 0.14 255);
  --color-purple-400: oklch(60% 0.16 300);
  --color-purple-600: oklch(48% 0.14 300);
  --color-cyan-400:   oklch(70% 0.12 195);
  --color-cyan-600:   oklch(55% 0.10 195);

  /* 间距 */
  --spacing-0-5: 2px;
  --spacing-1:   4px;
  --spacing-1-5: 6px;
  --spacing-2:   8px;
  --spacing-3:   12px;
  --spacing-4:   16px;
  --spacing-5:   20px;
  --spacing-6:   24px;
  --spacing-8:   32px;
  --spacing-10:  40px;
  --spacing-12:  48px;

  /* 圆角 */
  --radius-sm:   6px;
  --radius-md:   8px;
  --radius-lg:   12px;
  --radius-xl:   16px;
  --radius-full: 9999px;

  /* 动效 */
  --duration-fast:   120ms;
  --duration-normal: 200ms;
  --duration-slow:   350ms;
  --ease-default:    cubic-bezier(0.4, 0, 0.2, 1);
  --ease-in:         cubic-bezier(0.4, 0, 1, 1);
  --ease-out:        cubic-bezier(0, 0, 0.2, 1);

  /* 字重 */
  --font-weight-normal: 400;
  --font-weight-medium: 500;
  --font-weight-semibold: 600;

  /* 字号 */
  --text-xs:   10px;
  --text-sm:   12px;
  --text-base: 13px;
  --text-md:   14px;
  --text-lg:   16px;
  --text-xl:   18px;
  --text-2xl:  20px;
  --text-3xl:  24px;
  --text-4xl:  28px;
}
```

### 4.2 L2 Semantic（语义表面）

**原则**：引用 L1 原语，描述「用途」。暗色模式值直接定义。

```css
/* 02-semantic.css */
@theme inline {
  /* 表面层级 */
  --color-surface-0:   oklch(12% 0.006 254);
  --color-surface-1:   oklch(16% 0.008 254);
  --color-surface-2:   oklch(20% 0.009 254);
  --color-surface-3:   oklch(24% 0.010 254);
  --color-surface-4:   oklch(28% 0.011 254);
  --color-surface-5:   oklch(34% 0.012 254);

  /* 文本层级 */
  --color-foreground:       oklch(97% 0.005 254);
  --color-foreground-secondary: oklch(86% 0.009 254);
  --color-foreground-tertiary:  oklch(58% 0.012 254);
  --color-foreground-muted:     oklch(46% 0.012 254);
  --color-foreground-disabled:  oklch(38% 0.011 254);

  /* 边框 */
  --color-border:        oklch(28% 0.008 254);
  --color-border-subtle: oklch(22% 0.006 254);
  --color-border-strong: oklch(38% 0.010 254);

  /* 品牌强调 */
  --color-accent:        oklch(60% 0.18 255);
  --color-accent-fg:     oklch(99% 0.002 254);

  /* 签名色 — Brass */
  --color-brass-500:     oklch(72% 0.08 75);
  --color-brass-400:     oklch(78% 0.06 75);
  --color-brass-300:     oklch(84% 0.04 75);

  /* 代码 */
  --color-code-bg:       oklch(14% 0.008 280);
  --color-code-fg:       oklch(82% 0.06 280);

  /* 滚动条 */
  --color-scrollbar:     oklch(46% 0.012 254 / 0.3);
  --color-scrollbar-hover: oklch(58% 0.012 254 / 0.5);

  /* 分割线 */
  --color-divider:       oklch(28% 0.008 254 / 0.5);

  /* 遮罩 */
  --opacity-overlay:     0.5;
  --opacity-overlay-heavy: 0.75;

  /* 毛玻璃 */
  --blur-frosted:        12px;
}
```

**开发者使用**：
- `bg-surface-0` / `bg-surface-1` — 表面层级
- `text-foreground` / `text-foreground-secondary` — 文本层级
- `border-border` / `border-border-subtle` — 边框
- `text-accent` / `bg-accent` — 品牌强调

### 4.3 L3 Shell（布局尺寸）

**原则**：定义 Shell 组件的固定尺寸，不涉及颜色。

```css
/* 03-shell.css */
@theme inline {
  --width-rail:           60px;
  --width-rail-collapsed: 48px;
  --width-sidebar:        280px;
  --width-detail:         360px;
  --height-header:        48px;
  --height-bar:           36px;
  --height-bar-sm:        28px;
  --height-bar-lg:        42px;
}
```

### 4.4 L4 Data Viz（数据可视化）

**原则**：金融数据专用色。

```css
/* 04-data-viz.css */
@theme inline {
  /* 数据新鲜度 */
  --color-data-fresh:     oklch(97% 0.005 254 / 1);
  --color-data-recent:    oklch(97% 0.005 254 / 0.8);
  --color-data-stale:     oklch(97% 0.005 254 / 0.5);

  /* 图表系列色 */
  --color-chart-1: oklch(65% 0.15 255);
  --color-chart-2: oklch(70% 0.16 155);
  --color-chart-3: oklch(75% 0.15 85);
  --color-chart-4: oklch(60% 0.16 300);
  --color-chart-5: oklch(70% 0.12 195);
  --color-chart-6: oklch(80% 0.10 60);

  /* 热力图 */
  --color-heatmap-0: oklch(30% 0.04 254);
  --color-heatmap-1: oklch(45% 0.08 255);
  --color-heatmap-2: oklch(55% 0.12 255);
  --color-heatmap-3: oklch(65% 0.16 255);
  --color-heatmap-4: oklch(72% 0.18 255);

  /* Sparkline */
  --color-sparkline: oklch(60% 0.18 255);
  --color-sparkline-negative: oklch(65% 0.20 25);

  /* 资产类别 — Paul Tol 色板 */
  --color-asset-equity:  oklch(65% 0.15 30);
  --color-asset-bond:    oklch(60% 0.12 255);
  --color-asset-commodity: oklch(70% 0.14 85);
  --color-asset-fx:      oklch(65% 0.10 195);
  --color-asset-crypto:  oklch(60% 0.16 300);
  --color-asset-derivative: oklch(55% 0.08 150);

  /* 状态 LED */
  --color-led-active:   oklch(70% 0.16 155);
  --color-led-idle:     oklch(75% 0.15 85);
  --color-led-error:    oklch(65% 0.20 25);
}
```

### 4.5 L5 Component（组件结构）

**原则**：组件级结构 token（尺寸、间距），非颜色。

```css
/* 05-component.css */
@theme inline {
  /* Button */
  --height-btn-sm:  28px;
  --height-btn-md:  34px;
  --height-btn-lg:  40px;
  --radius-btn:     var(--radius-md);
  --padding-btn-sm: 0 var(--spacing-2);
  --padding-btn-md: 0 var(--spacing-3);
  --padding-btn-lg: 0 var(--spacing-4);

  /* Badge / Tag / Chip */
  --height-badge:    20px;
  --padding-badge:   0 var(--spacing-1-5);
  --radius-badge:    var(--radius-full);

  /* Card / Panel */
  --radius-card:     var(--radius-lg);
  --padding-card:    var(--spacing-4);

  /* Input / Select */
  --height-input:    34px;
  --radius-input:    var(--radius-md);
  --padding-input:   var(--spacing-0-5) var(--spacing-2);

  /* Tab */
  --height-tab:      36px;
  --radius-tab:      var(--radius-sm);

  /* Checkbox */
  --size-checkbox:   16px;
  --radius-checkbox: var(--radius-sm);
}
```

### 4.6 L6 Interaction（交互反馈）

```css
/* 06-interaction.css */
@theme inline {
  /* Focus */
  --color-focus-ring: oklch(60% 0.18 255);
  --width-focus-ring: 2px;

  /* Hover / Active / Selected */
  --opacity-hover:    0.08;
  --opacity-active:   0.12;
  --opacity-selected: 0.16;

  /* Toast / Banner */
  --color-toast-info:    oklch(65% 0.15 255);
  --color-toast-success: oklch(70% 0.16 155);
  --color-toast-warning: oklch(75% 0.15 85);
  --color-toast-error:   oklch(65% 0.20 25);

  /* Progress */
  --color-progress:     oklch(60% 0.18 255);
  --height-progress:    2px;
}
```

### 4.7 L7 Domain（业务域语义）

**原则**：金融业务域专用色，CN 默认（红涨绿跌）。

```css
/* 07-domain.css */
@theme inline {
  /* 市场 — CN 默认：红涨绿跌 */
  --color-market-up:      oklch(65% 0.20 25);
  --color-market-down:    oklch(70% 0.16 155);
  --color-market-flat:    oklch(58% 0.012 254);
  --color-market-limit-up: oklch(70% 0.22 25);
  --color-market-limit-down: oklch(55% 0.14 155);

  /* 风控 */
  --color-risk-critical:  oklch(65% 0.20 25);
  --color-risk-high:      oklch(70% 0.18 40);
  --color-risk-warning:   oklch(75% 0.15 85);
  --color-risk-moderate:  oklch(75% 0.12 195);
  --color-risk-normal:    oklch(70% 0.16 155);
  --color-risk-info:      oklch(65% 0.15 255);

  /* 交易 */
  --color-execution-filled:   oklch(70% 0.16 155);
  --color-execution-partial:  oklch(75% 0.15 85);
  --color-execution-pending:  oklch(75% 0.12 195);
  --color-execution-cancelled: oklch(58% 0.012 254);
  --color-execution-rejected: oklch(65% 0.20 25);

  /* AI Agent */
  --color-agent-running:   oklch(65% 0.15 255);
  --color-agent-idle:      oklch(58% 0.012 254);
  --color-agent-error:     oklch(65% 0.20 25);
  --color-agent-success:   oklch(70% 0.16 155);
  --color-agent-thinking:  oklch(70% 0.12 195);

  /* 系统状态 */
  --color-system-healthy:  oklch(70% 0.16 155);
  --color-system-degraded: oklch(75% 0.15 85);
  --color-system-down:     oklch(65% 0.20 25);

  /* 数据质量 */
  --color-quality-good:    oklch(70% 0.16 155);
  --color-quality-delayed: oklch(75% 0.15 85);
  --color-quality-stale:   oklch(65% 0.20 25);

  /* 信号 */
  --color-signal-buy:      oklch(65% 0.20 25);
  --color-signal-sell:     oklch(70% 0.16 155);
  --color-signal-hold:     oklch(75% 0.15 85);
}
```

### 4.8 L8 Density（密度预设）

**原则**：不用 `@theme inline`，用 `:root` 属性选择器覆盖。

```css
/* 08-density.css */
:root {
  --row-height:     36px;
  --cell-gap:       var(--spacing-2);
  --cell-padding-y: var(--spacing-1);
  --font-delta:     0;
  --section-gap:    var(--spacing-4);
  --list-gap:       var(--spacing-1);
}

[data-density="comfortable"] {
  --row-height:     42px;
  --cell-padding-y: var(--spacing-1-5);
  --section-gap:    var(--spacing-6);
  --list-gap:       var(--spacing-1-5);
}

[data-density="dense"] {
  --row-height:     34px;
  --cell-padding-y: var(--spacing-0-5);
  --font-delta:     -1;
  --section-gap:    var(--spacing-3);
  --list-gap:       var(--spacing-0-5);
}
```

## 5. 主题覆盖系统

### 5.1 主题切换机制

通过 HTML 属性切换：

```html
<html data-theme="dark" data-density="compact" data-market-region="cn">
```

- `data-theme`: `dark`（默认）| `light`
- `data-density`: `compact`（默认）| `comfortable` | `dense`
- `data-market-region`: `cn`（默认）| `intl`

### 5.2 dark.css（暗色 — 默认）

暗色主题值已在 L2-L7 各层的 `@theme inline` 中直接定义，此文件可空或仅包含显式声明。

### 5.3 light.css（亮色覆盖）

```css
/* themes/light.css */
[data-theme="light"] {
  /* 表面 */
  --color-surface-0:   oklch(99% 0.002 254);
  --color-surface-1:   oklch(97% 0.005 254);
  --color-surface-2:   oklch(93% 0.007 254);
  --color-surface-3:   oklch(90% 0.008 254);
  --color-surface-4:   oklch(86% 0.009 254);
  --color-surface-5:   oklch(80% 0.010 254);

  /* 文本 */
  --color-foreground:       oklch(14% 0.006 254);
  --color-foreground-secondary: oklch(30% 0.010 254);
  --color-foreground-tertiary:  oklch(46% 0.012 254);
  --color-foreground-muted:     oklch(58% 0.012 254);
  --color-foreground-disabled:  oklch(74% 0.011 254);

  /* 边框 */
  --color-border:        oklch(86% 0.009 254);
  --color-border-subtle: oklch(90% 0.008 254);
  --color-border-strong: oklch(74% 0.011 254);

  /* 代码 */
  --color-code-bg:       oklch(95% 0.008 280);
  --color-code-fg:       oklch(20% 0.06 280);
}
```

### 5.4 market-intl.css（国际市场色覆盖）

```css
/* themes/market-intl.css */
[data-market-region="intl"] {
  /* 国际惯例：绿涨红跌 */
  --color-market-up:      oklch(70% 0.16 155);
  --color-market-down:    oklch(65% 0.20 25);
  --color-market-limit-up: oklch(55% 0.14 155);
  --color-market-limit-down: oklch(70% 0.22 25);
}
```

## 6. 命名规范

### 6.1 通用规则

| 规则 | 示例 |
|------|------|
| kebab-case | `--color-surface-0` |
| 颜色用 `--color-` 前缀 | `--color-accent` |
| 间距用 `--spacing-` 前缀 | `--spacing-4` |
| 圆角用 `--radius-` 前缀 | `--radius-md` |
| 动效用 `--duration-` / `--ease-` 前缀 | `--duration-fast` |
| 组件尺寸用 `--{dimension}-{component}-{variant}` | `--height-btn-md` |
| 域语义用 `--color-{domain}-{state}` | `--color-risk-critical` |

### 6.2 Tailwind 命名空间映射

| 前缀 | Tailwind 工具类 | 示例 |
|------|---------------|------|
| `--color-*` | `bg-*` `text-*` `border-*` `ring-*` | `bg-surface-0` `text-foreground` |
| `--spacing-*` | `p-*` `m-*` `w-*` `h-*` `gap-*` | `p-4` `gap-2` |
| `--radius-*` | `rounded-*` | `rounded-md` |
| `--width-*` / `--height-*` | `w-*` `h-*` `max-w-*` | `w-rail` `h-header` |
| `--duration-*` | `duration-*` | `duration-fast` |
| `--ease-*` | `ease-*` | `ease-default` |
| `--text-*` | `text-*` (font-size) | `text-sm` `text-base` |

### 6.3 反模式（禁止）

| 禁止 | 原因 | 替代 |
|------|------|------|
| `--color-bg-surface-0` | bg/bg 冗余 | `--color-surface-0` |
| `--text-primary-color` | 混合命名空间 | `--color-foreground` |
| `--my-custom-blue` | 无结构命名 | `--color-brand-500` |
| `oklch(60% 0.18 255)` 在组件中 | 魔法值 | 引用 token |

## 7. 迁移策略

### 7.1 Token 映射表（原型 → 运行时）

| 原型命名 | 运行时命名 | 变化 |
|----------|-----------|------|
| `--bg-surface-0` | `--color-surface-0` | 去冗余 + 加命名空间 |
| `--fg-primary` | `--color-foreground` | shadcn 风格 |
| `--fg-secondary` | `--color-foreground-secondary` | 统一前缀 |
| `--border-default` | `--color-border` | 简化 |
| `--neutral-50` | `--color-neutral-50` | 加命名空间 |
| `--spacing-1` | `--spacing-1` | 不变 |
| `--radius-sm` | `--radius-sm` | 不变 |
| `--shell-rail-width` | `--width-rail` | 统一尺寸前缀 |
| `--domain-bg-green` | 直接引用 `--color-market-down` | 去中间变量 |

### 7.2 执行步骤

1. **创建目录**：`src/styles/tokens/` + `src/styles/themes/`
2. **提取 + 重写**：从原型 8 个 token 文件提取变量，按映射表重写为 `@theme inline` 格式
3. **拆分主题**：从原型中提取 dark/light/intl 覆盖到独立文件
4. **重写 globals.css**：替换现有 token 为 `@import` 模式
5. **验证**：`bun run check` + 浏览器视觉回归

### 7.3 风险点

- **`oklch(from ...)` 相对颜色语法**：原型中使用了 CSS Relative Color Syntax，需确认浏览器支持范围。降级方案：展开为绝对值。
- **L7 Domain DRY 中间变量**（`--domain-bg-green`）：运行时不再使用，直接引用最终语义 token。
- **Style B 覆盖**（tokens-style.css）：合并到 dark.css / light.css 主题文件中。

## 8. 业界参考

| 来源 | 模式 | 参考点 |
|------|------|--------|
| **W3C DTCG v2025.10** | JSON Token 标准 | 命名规范、类型系统、$value/$type 格式 |
| **shadcn/ui** | CSS 唯一真源 + `@theme inline` | 本项目直接采用的模式 |
| **Tailwind v4** | CSS-first config | `@theme` 命名空间映射机制 |
| **Martin Fowler** | Token-Based UI Architecture | 三层架构（Primitive → Semantic → Component）|
| **Style Dictionary** | 构建管线 | 未来如需多平台可引入 |

## 9. 未来演进

| 阶段 | 时机 | 内容 |
|------|------|------|
| **Phase 1**（当前） | 立即 | CSS 唯一真源，从原型迁移 |
| **Phase 2** | 组件开发时 | L5 Component token 随组件逐步补充 |
| **Phase 3** | 如需 Figma 协作 | 引入 Tokens Studio + Style Dictionary，从 CSS 逆向生成 JSON |
| **Phase 4** | 如需多平台 | JSON 做源，CSS 变为生成产物 |
