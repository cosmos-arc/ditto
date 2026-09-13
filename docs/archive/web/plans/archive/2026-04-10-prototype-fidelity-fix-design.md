# 原型保真度修复计划 — Graphite Studio 视觉基线对齐

> **日期**：2026-04-10
> **状态**：执行中（Phase 0-4 已完成，Phase 5 已完成）
> **执行范围**：Phase 0 → Phase 1 + 2 并行 → Phase 3 → Phase 4 → Phase 5 ✅

## Context

当前实现与原型（16 页，均分 9.0+）差距巨大：视觉保真度 < 20%，核心材质感层（噪点、环境光、磨砂玻璃）全部缺失或实现错误，数据表格退化为列表，11 个 JS 交互模块无 React 等效组件，7/12 共享组件引用未定义的 token。

**目标**：通过 5 个 Phase，将实现逐步对齐到原型的视觉和交互标准。每个 Phase 产出可验证的增量。

---

## Phase 0: Token 基线修复（所有后续工作的前提）

**问题**：7/12 共享组件引用了不存在的 CSS token（`--space-*`、`--font-size-*`、`--color-foreground-primary`），导致样式静默失效。

### 0.1 创建 Token 别名映射

在 `src/styles/tokens/01-primitives.css` 末尾添加别名，使两套命名兼容：

```css
/* --- 兼容别名（组件引用的旧命名 → 实际 token） --- */
--space-6: var(--spacing-1-5);   /* 6px */
--space-8: var(--spacing-2);     /* 8px */
--space-10: var(--spacing-2-5);  /* 10px */
--space-12: var(--spacing-3);    /* 12px */
--space-16: var(--spacing-4);    /* 16px */
--font-size-10: var(--text-xs);  /* 10px */
--font-size-12: var(--text-sm);  /* 12px */
--font-size-13: var(--text-base);/* 13px */
--font-size-14: var(--text-md);  /* 14px */
--color-foreground-primary: var(--color-foreground);
--color-brand-accent: var(--color-accent);
```

### 0.2 修复 token 引用错误

| 文件 | 错误 | 修正 |
|------|------|------|
| `components/domain/market-card/market-card.tsx` | `--radius-6` | `--radius-sm` |
| `components/indicator/confidence-bar/confidence-bar.tsx` | `--color-brand-accent` | `--color-accent` |
| `components/data/metric/metric.tsx` | 硬编码 `text-[10px]` 等 | 使用 `text-(--text-xs)` 等 token |

### 0.3 验证

- `bunx tsc --noEmit` 通过
- 所有 token 引用在 CSS 中有定义
- 浏览器中组件样式不再静默失效

**文件清单**：
- `src/styles/tokens/01-primitives.css` — 添加别名
- `src/components/data/metric/metric.tsx` — 硬编码字号 → token
- `src/components/domain/market-card/market-card.tsx` — `--radius-6` → `--radius-sm`
- `src/components/indicator/confidence-bar/confidence-bar.tsx` — `--color-brand-accent` → `--color-accent`

---

## Phase 1: Shell 视觉基线（材质感 + 交互基础）

**问题**：原型的 "Graphite Studio" 品牌感由多层视觉效果构建（噪点纹理、环境光线、磨砂玻璃、focus ring、入场动画），实现中全部缺失或简化。

### 1.1 修复 NoiseLayer 环境光

当前实现用 128px 渐变带替代原型 1.5px/1px 的光线，视觉差异巨大。

**文件**：`src/features/shell/components/noise-layer.tsx`

- 顶部光线：`h-32 from-brand-500/5` → `h-[1.5px]` + `color-mix(in oklch, var(--color-accent) 10%~18%, transparent)` 渐变
- 右侧光线：`w-32 from-brand-500/5` → `w-[1px]` + 同上 `color-mix` 渐变
- 保留噪点纹理（参数已正确）

### 1.2 Header 磨砂玻璃 + 签名线

**文件**：`src/features/shell/components/header.tsx`

- 添加 `backdrop-blur-[12px]` + `bg-[var(--color-surface-frosted)]`
- 添加 `::after` 伪元素实现底部签名渐变线（可通过 Tailwind `after:` 前缀或 `globals.css` 全局规则）
- 需确认 `--color-surface-frosted` token 已定义（`02-semantic.css` 中有 `--color-surface-frosted`）

### 1.3 Focus-Visible Ring 系统

**文件**：`src/styles/globals.css`

添加全局 focus-visible 规则：

```css
[data-slot="panel"] button:focus-visible,
[data-slot="rail"] button:focus-visible,
[data-slot="header"] button:focus-visible,
[data-slot="decision-banner"] button:focus-visible {
  outline: none;
  box-shadow: 0 0 0 1.5px var(--color-accent), 0 0 0 4px oklch(from var(--color-accent) l c h / 0.25);
  border-radius: var(--radius-sm);
}
```

### 1.4 入场动画 Keyframes

**文件**：`src/styles/globals.css`

添加缺失的 keyframes：

- `dot-critical-pulse`（opacity 1→0.4, 2s）
- `value-flash`（translateY + opacity, 400ms）
- `conclusion-appear`（translateY(4px) + opacity, 600ms）
- `tab-reveal`（translateY(4px) + opacity, 200ms）
- `status-breathe`（opacity 0.7→1, 2s）

### 1.5 Rail 活跃指示器光晕

**文件**：`src/features/shell/components/rail.tsx`

- 活跃状态左侧 3px 指示条添加 `box-shadow: 0 0 6px var(--color-accent)` 光晕

### 1.6 验证

- Home 页面 Shell 层视觉效果与原型匹配（噪点、环境光、磨砂玻璃、focus ring）
- `bun run check` 通过

---

## Phase 2: 核心交互组件（React 化原型 JS 模块）

**问题**：原型有 11 个 JS 交互模块（sparkline/ticker/tooltip/glow 等），实现中几乎无对应 React 组件。

### 2.1 Tooltip 组件

使用 shadcn/ui 的 Radix Tooltip（已有依赖）。

**新建**：`src/components/ui/tooltip.tsx`（如不存在则 `bunx shadcn@latest add tooltip`）

封装为 `<DittoTooltip>` 组件，匹配原型的样式：
- `bg-[var(--color-surface-overlay)]` + `border border-[var(--color-border-default)]`
- `shadow-[0_4px_12px_oklch(0_0_0/0.3)]`
- `text-xs leading-snug max-w-[240px]`
- 渐入 150ms

### 2.2 Sparkline 升级（Catmull-Rom）

**文件**：`src/components/data/sparkline/sparkline.tsx`

- 将 `<polyline>` 线性插值升级为 Catmull-Rom 样条曲线（平滑路径）
- 修复 gradient ID 冲突（使用 `useId()`）
- 保持现有 props API 不变

算法参考：`prototype/shared/prototype-interactions.js` lines 94-173

### 2.3 NumberTicker 组件

**新建**：`src/components/data/number-ticker.tsx`

React 组件，props：
- `value: string | number`
- `decimals?: number`
- `prefix?: string`
- `suffix?: string`
- `duration?: number` (default 1200ms)

使用 `IntersectionObserver` + `requestAnimationFrame` + ease-out cubic 缓动。匹配原型的 `data-ticker` 行为。

### 2.4 MouseGlow Hook

**新建**：`src/hooks/use-mouse-glow.ts`

返回 `[ref, handlers]`，在元素上设置 `--_glow-x` 和 `--_glow-y` CSS 变量。组件通过 CSS `radial-gradient(circle 200px at var(--_glow-x) var(--_glow-y), ...)` 使用。

### 2.5 FlowBar 组件

**新建**：`src/components/data/flow-bar.tsx`

分段水平条形图，props：
- `segments: readonly { value: number; label?: string; color?: string }[]`
- `height?: number` (default 6px)
- `trackClassName?: string`

匹配原型的 `.flow-bar-track` / `.flow-bar-fill` 样式。

### 2.6 DonutGauge 组件

**新建**：`src/components/data/donut-gauge.tsx`

SVG 环形进度，props：
- `value: number` (0-1)
- `label?: string`
- `size?: number` (default 64)
- `color?: string`

### 2.7 验证

- 所有新组件有单元测试（覆盖率 ≥ 80%）
- `bun run check` 通过
- 在页面中验证视觉效果

---

## Phase 3: 数据展示升级（列表 → 表格 + 条件格式）

**问题**：因子表、持仓表等核心数据展示退化为简单 flex 列表，缺少排序、条件格式、spark bar、行状态。

### 3.1 通用 DataTable 组件

**新建**：`src/components/data/data-table.tsx`

基于原型 `layout-base.css` 的 `.data-table` 模式，提供：
- `<table>` 语义化结构 + `table-layout: fixed`
- Sticky `<thead>` + 可排序列（`<th>` 点击排序 + 三角指示器）
- 行 hover/selected 状态
- 数字列自动使用 `font-data tabular-nums`
- 条件格式支持（通过 cell renderer props）
- Density 响应（cell padding 跟随 `--density-cell-padding-x/y`）

Props 设计：
```tsx
interface DataTableProps<T> {
  columns: ColumnDef<T>[]
  data: readonly T[]
  onRowClick?: (row: T) => void
  selectedId?: string
  density?: 'default' | 'comfortable' | 'dense'
}
```

### 3.2 FactorTable 升级

**文件**：`src/features/research/components/factor-table.tsx`

从 flex 列表 → DataTable：
- 10 列：status bar | factor(category+name) | IC | IR | Sharpe | Turnover | Decay | Coverage | Universe | Status
- IC 条件格式：4 级颜色（strong/normal/muted/dim）+ spark bar
- IR 条件格式：同上 4 级
- IC heatmap 背景（`::before` 伪元素，brand-accent 不同透明度）
- 行状态条（左侧 2px 色条：degraded=amber, down=red, brand=accent）
- Sharpe 趋势箭头（trend-up/down/flat）
- Status 列内联 sparkline

### 3.3 PositionsSummary 升级

**文件**：`src/features/trading/components/positions-summary.tsx`

从 div 列表 → DataTable：
- 8 列：code | name | qty | cost | current | 7D sparkline | PnL | PnL%
- 条件行底色（positive → market-up 4%, negative → market-down 4%）
- 表头 accent border（`border-bottom: 2px solid color-mix(in oklch, var(--color-accent) 35%, transparent)`）
- 汇总行（total PnL/PnL%）

### 3.4 验证

- Research 页面因子表与原型对比：10 列、条件格式、排序
- Trading 页面持仓表与原型对比：8 列、sparkline、行底色
- `bun run check` 通过

---

## Phase 4: 页面区域补全（缺失面板 + 布局对齐）

**问题**：多个原型的完整页面区域（Decision Banner、Right Rail、Analysis Band、Status Bar、Context Bar）在实现中缺失。

### 4.1 可复用 ContextBar 组件

**新建**：`src/components/indicator/context-bar.tsx`

统一替代各页面内联的 context bar，提供：
- `<ContextBar>` 容器 + `<ContextBarItem>` 子组件
- label/value 结构（label uppercase 10px, value 12px medium）
- 分隔线 `<ContextBarSep>`
- 磨砂玻璃变体（`backdrop-blur-[12px]`）
- Regime 颜色编码（on=market-up, off=market-down, mixed=amber）

### 4.2 Decision Banner 完善

**文件**：`src/components/domain/decision-banner/decision-banner.tsx`

当前实现只有 judgment 中的 1 个 metric，需要：
- Primary 区：补齐 inline sparkline（使用升级后的 Sparkline 组件）
- Judgment 区：补齐 KPI row（杠杆率 + 回撤）+ 额外 metrics（IVIX + 北向资金 sparkline）
- Actions 区：确保 CTA 按钮被传入并渲染

### 4.3 Trading 页面补全

**文件**：`src/features/trading/components/trading-page.tsx`

- 补充 Decision Banner 行（prototype 的 `trading-banner` grid area）
- 补充 Orders 面板（待成交/已成交/已撤单 tab + 订单行 + 状态视觉区分）
- 补充最近成交区域
- Signal queue 优先级条渐变 + 光晕
- Risk monitoring 进度条渐变 + threshold marker

### 4.4 Markets 页面补全

**文件**：`src/features/markets/components/markets-page.tsx`

- 替换内联 ContextBar → 可复用 `<ContextBar>` 组件
- 补充 Scope Strip（今日解读）
- 补充 Cross-Market Matrix（相关矩阵 + 热力图）
- Macro Drivers 从卡片布局 → 原型内联条式布局
- Capital Rotation 从文本行 → FlowBar 可视化

### 4.5 Research Analysis Band 补全

**文件**：`src/features/research/components/research-page.tsx`

- 替换 placeholder → 4 tab 分析面板（IC Trends / Factor Width / Correlation / Notes）
- IC Trends：指标摘要行 + SVG 面积图
- Correlation：5x5 热力图矩阵
- Factor Width：柱状图
- Notes：笔记列表

### 4.6 StatusBar 组件

**新建**：`src/features/shell/components/status-bar.tsx`

- VS Code 风格底栏：LIVE 指示灯 + 连接状态 + 延迟 + 时间 + 快捷键提示
- `fixed bottom-0 left-[var(--width-rail)] right-0`
- `backdrop-blur-[8px]` + `h-[var(--height-status-bar)]`
- 集成到 `AppShell`

### 4.7 验证

- Trading 页面布局匹配原型（banner + orders + fills + risk）
- Markets 页面布局匹配原型（context bar + scope strip + matrix + right rail 占位）
- Research 分析带从 placeholder → 4 tab 实际内容
- StatusBar 在所有页面显示
- `bun run check` 通过

---

## Phase 5: 精修 + 交互打磨

### 5.1 Header Theme/Density 切换器

**新建**：`src/features/shell/components/theme-switcher.tsx`

- Density 切换：3 按钮（紧/标/松），设置 `data-density` 属性
- Theme 切换：2 按钮（暗/亮），设置 `data-theme` 属性
- Zustand store 持久化到 localStorage
- 集成到 ShellHeader

### 5.2 入场动画集成

- 使用 `useScrollReveal` hook（基于 `IntersectionObserver`）实现 `data-reveal` 等效
- 面板 staggered entrance（fade-up, 0/60/120ms delay）
- 卡片 grid entrance

### 5.3 Hover 微交互

- Panel hover 光晕（已有 `globals.css` 中的 `[data-slot="panel"]:hover`）
- Queue item hover 负 margin 扩展效果
- Market card hover `box-shadow: inset 0 0 0 1px`
- Context section hover 品牌色微光

### 5.4 Typography 精修

- 所有数字区域统一 `font-data tabular-nums` + `letter-spacing: -0.02em`
- Pulse strip / Context bar label → uppercase + `tracking-wide`
- 确保 12px 在表格/列表中替代当前的 `text-sm`（14px）

### 5.5 验证

- 逐页与原型截图对比（Home、Research、Trading、Markets、Platform）
- `bun run check` 通过
- 覆盖率 ≥ 80%

---

## 执行策略

| Phase | 预估复杂度 | 依赖 | 可并行 |
|-------|-----------|------|--------|
| Phase 0 | 低 | 无 | 否（前提） |
| Phase 1 | 中 | Phase 0 | Phase 2 可并行 |
| Phase 2 | 中高 | Phase 0 | 与 Phase 1 并行 |
| Phase 3 | 高 | Phase 0 + 2 | 否 |
| Phase 4 | 高 | Phase 1 + 2 + 3 | 部分可并行 |
| Phase 5 | 中 | Phase 4 | 否 |

**执行顺序**：Phase 0 → Phase 1 + 2 并行 → Phase 3 → Phase 4 → Phase 5

每个 Phase 完成后运行 `bun run check` 验证，确认无回归再进入下一 Phase。

---

## 差距诊断摘要

### 五大核心差距

1. **材质感层完全缺失** — 噪点纹理、环境光线（128px 带 vs 1.5px 线）、磨砂玻璃、focus ring、入场动画
2. **数据可视化全面缺失** — Sparkline(14+)、NumberTicker(73)、Tooltip(300)、MouseGlow(42)、DonutGauge(14)、HeatGrid(6)、FlowBar(9)
3. **数据表格退化为列表** — FactorTable(10列→3列)、PositionsTable(8列→5列)、OrdersPanel(缺失)、CorrelationMatrix(缺失)
4. **整个页面区域缺失** — DecisionBanner(Trading)、RightRail(Markets)、AnalysisBand(Research)、StatusBar(全局)、ThemeSwitcher(Header)
5. **Typography/Spacing 不一致** — 两套 token 命名共存、`text-sm`(14px) 替代 `font-size-12`(12px)、数字区无 `tabular-nums`

### 组件 token 缺失清单

| 未定义 Token | 引用组件 | 应映射到 |
|---|---|---|
| `--space-6/8/10/12/16` | DecisionBanner, ContextSection, MarketCard, AlertRow, ScopeStrip | `--spacing-1-5/2/2-5/3/4` |
| `--font-size-10/12/13/14` | DecisionBanner, ContextSection, MarketCard, AlertRow, Drawer, ConfidenceBar | `--text-xs/sm/base/md` |
| `--color-foreground-primary` | DecisionBanner, ContextSection, MarketCard, AlertRow, Drawer | `--color-foreground` |
| `--color-brand-accent` | ConfidenceBar | `--color-accent` |
| `--radius-6` | MarketCard | `--radius-sm` |
