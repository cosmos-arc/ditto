# Phase 3: 共享业务组件 Tier 4 — 域组件

## 概述
- Sprint: Phase 3 | 共享组件分层建设
- 创建: 2026-04-08
- 前置: [2026-04-08-phase2-tier3-components.md](./2026-04-08-phase2-tier3-components.md) ✅ 完成（26 files, 341 tests）
- 设计: [2026-04-08-shared-component-layer-design.md](./2026-04-08-shared-component-layer-design.md) §7
- 范围: ContextSection / FilterControls / Timeline / DecisionBanner / MarketCard

## 技术方案

### 关键决策
| 决策 | 选择 | 理由 |
|------|------|------|
| ContextSection | 基于 shadcn Collapsible 封装 | 已有 Collapsible 组件，避免重复造轮子 |
| FilterControls | FilterChip + FilterToolbar 容器 | 原型有两种模式（chip 组 + segmented），先做 chip |
| Timeline | 通用 TimelineItem 列表 + marker 变体 | 首期实现 default + activity，status/regime 逐页补充 |
| DecisionBanner | 3 列 grid 布局组合 Phase 1/2/3 组件 | 仅 2 页使用，组合复用 Metric/StatusBadge/Sparkline |
| MarketCard | 卡片组件组合 Phase 1/2 组件 | 仅 1 页使用，组合 Metric/StatusBadge/Sparkline |

### 执行依赖链
```
T1 ContextSection ─────────────────────────┐  (依赖 shadcn Collapsible，已有)
T2 FilterControls ─────────────────────────┤  (无依赖)
T3 Timeline ───────────────────────────────┤  (依赖 StatusDot)
T4 DecisionBanner ─────────────────────────┤  (依赖 Metric, StatusBadge, Sparkline, ConfidenceBar)
T5 MarketCard ─────────────────────────────┘  (依赖 Metric, StatusBadge, Sparkline)
```

T1/T2/T3 可并行，T4/T5 各自独立。

---

## 任务清单

### T1: ContextSection 侧边栏可折叠面板 `[S]`
- **复杂度**: S | 单文件 <80 行，基于 shadcn Collapsible
- **依赖**: shadcn Collapsible（已有）
- **文件**:
  - `src/components/domain/context-section/context-section.tsx`
  - `src/components/domain/context-section/context-section.test.tsx`
  - `src/components/domain/context-section/index.ts`
- **原型参考**: `shared/layout-base.css` L849-962
- **Props**:
  ```typescript
  interface ContextSectionProps extends React.HTMLAttributes<HTMLDivElement> {
    readonly title: string
    readonly count?: number
    readonly defaultOpen?: boolean  // 默认 true
    readonly action?: React.ReactNode
    readonly children: React.ReactNode
  }
  ```
- **样式映射**:
  - 容器: `flex flex-col min-h-0` + sections 之间 `border-t border-(--color-border-subtle)`
  - Header: `flex items-center justify-between py-[var(--space-8)] px-[var(--space-12)] shrink-0 cursor-pointer select-none`
  - Title: `text-(--font-size-12) font-medium text-(--color-foreground-tertiary) uppercase tracking-wide`
  - Count: `text-(--font-size-10) text-(--color-foreground-tertiary) font-data`
  - Action: `text-(--font-size-10) text-(--color-foreground-tertiary) hover:text-(--color-foreground-secondary) transition-colors`
  - Body: `flex-1 overflow-y-auto px-[var(--space-12)]`
  - Chevron indicator: `transition-transform duration-200` 旋转
- **验收**:
  - [ ] 渲染 title + 可选 count/action
  - [ ] defaultOpen=true 时显示 body 内容
  - [ ] defaultOpen=false 时隐藏 body 内容
  - [ ] 点击 header 切换展开/折叠
  - [ ] chevron 指示器随展开/折叠旋转
  - [ ] body 区域可滚动
  - [ ] barrel export

### T2: FilterControls 筛选控件组 `[S]`
- **复杂度**: S | 2 文件 <100 行
- **依赖**: 无
- **文件**:
  - `src/components/domain/filter-controls/filter-chip.tsx`
  - `src/components/domain/filter-controls/filter-chip.test.tsx`
  - `src/components/domain/filter-controls/filter-toolbar.tsx`
  - `src/components/domain/filter-controls/filter-toolbar.test.tsx`
  - `src/components/domain/filter-controls/index.ts`
- **原型参考**: `shared/layout-base.css` L1460-1579
- **FilterChip Props**:
  ```typescript
  interface FilterChipProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
    readonly label: string
    readonly active?: boolean
    readonly count?: number
  }
  ```
- **FilterToolbar Props**:
  ```typescript
  interface FilterToolbarProps extends React.HTMLAttributes<HTMLDivElement> {
    readonly children: React.ReactNode
  }
  ```
- **样式映射**:
  - Chip: `text-(--font-size-12) py-[var(--space-2)] px-[var(--space-8)] rounded-(--radius-4) border border-(--color-border-subtle) bg-transparent transition-colors duration-120`
  - Chip active: `border-(--color-brand-accent) bg-(--color-brand-accent) text-white`
  - Chip hover: `border-(--color-border-default) bg-(--color-interaction-hover-subtle-bg)`
  - Toolbar: `flex items-center gap-[var(--space-6)] bg-(--color-surface-1) border-b border-(--color-border-subtle) py-[var(--density-action-height)] px-[var(--space-12)]`
- **验收**:
  - [ ] FilterChip 渲染 label + 可选 count badge
  - [ ] FilterChip active 状态样式正确
  - [ ] FilterChip hover 状态样式
  - [ ] FilterToolbar 渲染 flex 容器
  - [ ] barrel export

### T3: Timeline 时间线 `[M]`
- **复杂度**: M | 2 文件 ~120 行
- **依赖**: StatusDot（Phase 1）
- **文件**:
  - `src/components/domain/timeline/timeline.tsx`
  - `src/components/domain/timeline/timeline.test.tsx`
  - `src/components/domain/timeline/index.ts`
- **原型参考**: `shared/layout-base.css` L3097, `page-risk-center.html` L573-658
- **Props**:
  ```typescript
  interface TimelineProps extends React.HTMLAttributes<HTMLDivElement> {
    readonly items: readonly TimelineItem[]
    readonly variant?: 'default' | 'activity'
  }

  interface TimelineItem {
    readonly id: string
    readonly marker?: 'dot' | 'event' | 'completed' | 'failed'
    readonly title: string
    readonly description?: string
    readonly time: string
    readonly status?: 'resolved' | 'monitoring' | 'triggered'
    readonly severity?: 'ok' | 'warn' | 'critical'
  }
  ```
- **样式映射**:
  - 容器: `flex flex-col`
  - Item: `flex gap-[var(--space-8)] py-[var(--space-8)] border-b border-(--color-border-subtle) last:border-b-0`
  - Time: `min-w-[50px] shrink-0 font-data text-(--font-size-12) text-(--color-foreground-tertiary)`
  - Title: `text-(--font-size-12) text-(--color-foreground-secondary) leading-snug`
  - Description: `text-(--font-size-10) text-(--color-foreground-tertiary) mt-0.5`
  - Status badge: 复用 `StatusDot` + label
  - Severity dot: 复用 `StatusDot`
- **验收**:
  - [ ] 渲染 items 列表
  - [ ] 每个 item 显示 time + title + 可选 description
  - [ ] severity 存在时显示 StatusDot
  - [ ] status 存在时显示状态标签
  - [ ] marker=dot 时显示连线样式
  - [ ] 空列表不报错
  - [ ] barrel export

### T4: DecisionBanner 决策横幅 `[M]`
- **复杂度**: M | 单文件 ~100 行
- **依赖**: Metric, StatusBadge, Sparkline, ConfidenceBar
- **文件**:
  - `src/components/domain/decision-banner/decision-banner.tsx`
  - `src/components/domain/decision-banner/decision-banner.test.tsx`
  - `src/components/domain/decision-banner/index.ts`
- **原型参考**: `shared/layout-base.css` L463-569
- **Props**:
  ```typescript
  interface DecisionBannerProps extends React.HTMLAttributes<HTMLDivElement> {
    readonly primary: {
      readonly label: string
      readonly value: string | number
      readonly sub?: string
      readonly trend?: 'up' | 'down' | 'flat'
      readonly sparkline?: readonly number[]
    }
    readonly judgment: {
      readonly text: string
      readonly regime?: { readonly label: string; readonly variant: import('@/components/status').BadgeVariant }
      readonly metrics: readonly { readonly label: string; readonly value: string; readonly trend?: 'up' | 'down' | 'flat' }[]
    }
    readonly actions?: readonly {
      readonly label: string
      readonly variant: 'primary' | 'secondary' | 'ghost'
      readonly onClick?: () => void
    }[]
  }
  ```
- **样式映射**:
  - 容器: `grid grid-cols-[5fr_4fr_3fr] gap-[var(--space-16)] py-[var(--space-12)] px-[var(--space-16)]`
  - 列分隔: 中间和右列 `border-l border-(--color-border-subtle) pl-[var(--space-16)]`
  - Primary: flex-col, label + value(sparkline) + sub
  - Judgment: flex-col, text + regime badge + kpi metrics
  - Actions: flex-col, items-end, CTA buttons
- **验收**:
  - [ ] 渲染 3 列 grid 布局
  - [ ] Primary 列显示 Metric + sparkline
  - [ ] Judgment 列显示 AI 判定文本 + regime badge + KPI metrics
  - [ ] Actions 列显示 CTA 按钮
  - [ ] 复用 Phase 1/2 组件（Metric, StatusBadge, Sparkline）
  - [ ] barrel export

### T5: MarketCard 市场卡片 `[S]`
- **复杂度**: S | 单文件 <80 行
- **依赖**: Metric, StatusBadge, Sparkline
- **文件**:
  - `src/components/domain/market-card/market-card.tsx`
  - `src/components/domain/market-card/market-card.test.tsx`
  - `src/components/domain/market-card/index.ts`
- **原型参考**: `page-cross-market.html` L294-395
- **Props**:
  ```typescript
  interface MarketCardProps extends React.HTMLAttributes<HTMLDivElement> {
    readonly name: string
    readonly regime: 'on' | 'off' | 'mixed'
    readonly index: string
    readonly change: number
    readonly judgment: string
    readonly sparkline?: readonly number[]
    readonly onClick?: () => void
  }
  ```
- **样式映射**:
  - Card: `flex flex-col gap-[var(--space-8)] p-[var(--space-12)] rounded-(--radius-6) border border-(--color-border-subtle) bg-(--color-surface-2) transition-colors duration-120 hover:bg-(--color-surface-3) hover:border-(--color-border-default)`
  - Top row: flex, justify-between, name + regime tag
  - Index: `font-data text-[24px] font-semibold tabular-nums`
  - Change: `font-data text-[13px] font-semibold` + trend color
  - Judgment: `text-(--font-size-12) text-(--color-foreground-tertiary) leading-normal`
  - Regime: 复用 StatusBadge
- **验收**:
  - [ ] 渲染卡片（name + regime + index + change + judgment）
  - [ ] regime 状态映射到 StatusBadge variant
  - [ ] change 正值绿色、负值红色
  - [ ] sparkline 存在时渲染 SVG 折线
  - [ ] hover 状态样式
  - [ ] barrel export

---

## 目录结构（新增）

```
src/components/
├── domain/                  # Tier 4 目录（新建）
│   ├── index.ts             # barrel export
│   ├── context-section/
│   │   ├── index.ts
│   │   ├── context-section.tsx
│   │   └── context-section.test.tsx
│   ├── filter-controls/
│   │   ├── index.ts
│   │   ├── filter-chip.tsx
│   │   ├── filter-chip.test.tsx
│   │   ├── filter-toolbar.tsx
│   │   └── filter-toolbar.test.tsx
│   ├── timeline/
│   │   ├── index.ts
│   │   ├── timeline.tsx
│   │   └── timeline.test.tsx
│   ├── decision-banner/
│   │   ├── index.ts
│   │   ├── decision-banner.tsx
│   │   └── decision-banner.test.tsx
│   └── market-card/
│       ├── index.ts
│       ├── market-card.tsx
│       └── market-card.test.tsx
```

---

## 执行顺序

```
并行启动 ───────────────────────────────────
│ T1 ContextSection   │ T2 FilterControls  │ T3 Timeline       │
│ (S)                 │ (S)                │ (M)               │
└─────────┬───────────┴─────────┬──────────┴─────────┬──────────┘
          │                     │                    │
          └──────────┬──────────┴────────────────────┘
                     ↓
          T4 DecisionBanner + T5 MarketCard（并行）
          (M)                   (S)
                     ↓
              Phase 3 验收
```

---

## Phase 验收标准

1. `bun run check` 全绿（lint + type + test）
2. 每个组件至少 3 个测试用例（渲染 / 变体 / 边界）
3. 所有样式使用 CSS 变量（Design Token），无硬编码像素值
4. barrel export 链路通畅：
   ```typescript
   import { ContextSection, FilterChip, FilterToolbar, Timeline, DecisionBanner, MarketCard } from "@/components/domain"
   ```
5. Tier 4 组件正确使用 Tier 2/2.5/3 组件组合
