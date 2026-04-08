# Phase 1: 共享业务组件 Tier 2 + Tier 2.5

## 概述
- Sprint: Phase 1 | 共享组件分层建设
- 创建: 2026-04-08
- 前置: [2026-04-08-shared-component-layer-design.md](./2026-04-08-shared-component-layer-design.md)
- 范围: Sparkline / Metric / StatusDot / StatusBadge / Boundary 系统 / DittoGrid

## 技术方案

### 关键决策
| 决策 | 选择 |
|------|------|
| Sparkline | 纯 SVG，无外部依赖 |
| Metric | CVA 变体（standard/strip/equity）× 尺寸（sm/md/lg） |
| StatusDot | CSS 变量映射，pulse 动画 |
| StatusBadge | dot + label 复合组件，CVA variant |
| Boundary | react-error-boundary + Suspense + StaleIndicator |
| DittoGrid | AG Grid Community v35 + DittoGrid 封装层 |

### 执行依赖链
```
T1 StatusDot ──→ T2 StatusBadge ──┐
T3 Sparkline ──→ T4 Metric ──────┼──→ T7 DittoGrid
T5 LoadingSkeleton ───────────────┤
T6 ErrorState + StaleIndicator ──┘
```

T1/T3/T5 可并行，T2/T4/T6 各依赖前置，T7 汇聚。

---

## 任务清单

### T1: StatusDot 状态指示灯 `[S]`
- **复杂度**: S | 单文件 <50 行
- **依赖**: 无
- **文件**:
  - `src/components/status/status-dot/status-dot.tsx`
  - `src/components/status/status-dot/status-dot.test.tsx`
  - `src/components/status/status-dot/index.ts`
- **验收**:
  - [ ] 渲染圆形 dot，默认 size=md (8px)
  - [ ] 支持 sm(6px) / md(8px) / lg(10px) 三种尺寸
  - [ ] 支持 healthy / degraded / warning / critical / live / idle / error / info 8 种 variant
  - [ ] 颜色映射到 `--status-led-{variant}` CSS 变量（回退到硬编码色值）
  - [ ] pulse=true 时 live variant 播放 CSS 脉冲动画（@keyframes dot-pulse）
  - [ ] 非 live variant 设置 pulse=true 不播放动画
  - [ ] barrel export: `export { StatusDot } from "./status-dot"`

### T2: StatusBadge 状态标签 `[M]`
- **复杂度**: M | 2 文件，~80 行，有 CVA 模式
- **依赖**: T1 (StatusDot)
- **文件**:
  - `src/components/status/status-badge/status-badge.tsx`
  - `src/components/status/status-badge/status-badge.test.tsx`
  - `src/components/status/status-badge/index.ts`
  - `src/components/status/index.ts`
- **验收**:
  - [ ] 渲染 dot + label 水平排列
  - [ ] 支持 17 种 variant（default / healthy / degraded / warning / critical / live / idle / error / trade / risk / research / platform / data / priority / regime-on / regime-off / regime-mixed / active / inactive）
  - [ ] 支持 sm / md 两种尺寸（md 默认）
  - [ ] dot 颜色映射到 `--status-led-{variant}` 或业务语义色
  - [ ] 背景色 = dot 颜色 8% 透明度
  - [ ] label 使用 `--font-size-10`（sm）/ `--font-size-12`（md）
  - [ ] barrel export: `export { StatusDot } from "./status-dot"` + `export { StatusBadge } from "./status-badge"`

### T3: Sparkline SVG 迷你折线图 `[M]`
- **复杂度**: M | 2 文件，~100 行，SVG path 计算
- **依赖**: 无
- **文件**:
  - `src/components/data/sparkline/sparkline.tsx`
  - `src/components/data/sparkline/sparkline.test.tsx`
  - `src/components/data/sparkline/index.ts`
- **验收**:
  - [ ] 渲染 `<svg>` 元素，默认 width=48 height=20
  - [ ] data 数组生成 `<polyline>` 折线
  - [ ] color='up' 映射 `--color-market-up`，'down' 映射 `--color-market-down`，'neutral' 映射 `--color-foreground-muted`
  - [ ] gradient=true 时生成 `<linearGradient>` + `<polygon>` 渐变填充区域
  - [ ] gradient=false 时只渲染折线，无填充
  - [ ] strokeWidth 默认 1.5
  - [ ] animate=true 时折线入场动画（CSS stroke-dasharray + dashoffset transition）
  - [ ] data 为空数组或单元素时优雅降级（不报错，渲染空 SVG）
  - [ ] data 仅 2 个点时渲染直线
  - [ ] barrel export

### T4: Metric KPI 指标展示 `[M]`
- **复杂度**: M | 2 文件，~120 行，CVA variant × size
- **依赖**: T3 (Sparkline)
- **文件**:
  - `src/components/data/metric/metric.tsx`
  - `src/components/data/metric/metric.test.tsx`
  - `src/components/data/metric/index.ts`
  - `src/components/data/index.ts`
- **验收**:
  - [ ] 渲染 label + value + 可选 sub 三行垂直排列
  - [ ] variant=standard：label 10px uppercase tertiary，value 16px numeric semibold，sub 10px tertiary
  - [ ] variant=strip：label + value 水平排列，label 10px tertiary，value 12px numeric medium
  - [ ] variant=equity：value 24px numeric semibold，sub 支持多行子项
  - [ ] size=sm：value 14px | size=md：value 16px | size=lg：value 24px
  - [ ] trend='up' 显示 ▲ + market-up 色，'down' 显示 ▼ + market-down 色，'flat' 显示 — + muted 色
  - [ ] sparkline prop 存在时在 value 右侧渲染 Sparkline 组件
  - [ ] value 支持 string | number，number 类型自动格式化千分位
  - [ ] barrel export: `export { Sparkline } from "./sparkline"` + `export { Metric } from "./metric"`

### T5: LoadingSkeleton 骨架屏 `[M]`
- **复杂度**: M | 2 文件，~100 行，5 种骨架变体
- **依赖**: 无
- **文件**:
  - `src/components/data/skeleton/loading-skeleton.tsx`
  - `src/components/data/skeleton/loading-skeleton.test.tsx`
  - `src/components/data/skeleton/index.ts`
- **验收**:
  - [ ] variant=panel：渲染 header shimmer (40% width, 16px height) + n 行 text shimmer (100% width, 12px height)
  - [ ] variant=table：渲染 header row (m 列等宽 shimmer) + n 行 data rows (m 列等宽 shimmer)
  - [ ] variant=card：渲染 title shimmer (40% width) + content area shimmer block
  - [ ] variant=metric：渲染 label shimmer (60% width, 10px) + value shimmer (40% width, 16px)
  - [ ] variant=chart：渲染大面积 shimmer block (160px height, 100% width)
  - [ ] shimmer 动画：`background-size: 200% 100%` + `@keyframes skeleton-shimmer` 1.5s ease-in-out infinite
  - [ ] shimmer 颜色：`--surface-muted` → `--surface-overlay` → `--surface-muted` 渐变
  - [ ] 所有 shimmer 元素使用 `border-radius: var(--radius-4)`
  - [ ] barrel export

### T6: ErrorState + StaleIndicator `[M]`
- **复杂度**: M | 3 文件，~120 行
- **依赖**: 无
- **文件**:
  - `src/lib/error-boundary.tsx` (ErrorBoundary 配置 + ErrorState 组件)
  - `src/lib/stale-indicator.tsx`
  - `src/lib/error-boundary.test.tsx`
  - `src/lib/stale-indicator.test.tsx`
- **新增依赖**: `react-error-boundary`
- **验收**:
  - [ ] ErrorState 组件：渲染图标 (40px 圆形) + title + description + 可选重试按钮
  - [ ] ErrorState 默认 title="加载失败"，支持自定义 title/description
  - [ ] ErrorState onRetry 存在时渲染 "重试" 按钮
  - [ ] ErrorState 图标使用 `bg-[var(--color-destructive)]/10` + destructive 色
  - [ ] StaleIndicator 组件：渲染顶部 2px 渐变条
  - [ ] StaleIndicator 渐变色：`brand-accent` 低透明度
  - [ ] StaleIndicator 使用 CSS transition 自动出现/消失
  - [ ] ErrorBoundary 导出配置好的 react-error-boundary 组件
  - [ ] `bun add react-error-boundary`

### T7: DittoGrid AG Grid 封装层 `[L]`
- **复杂度**: L | 5-6 文件，~300 行，跨模块
- **依赖**: T2 (StatusBadge), T3 (Sparkline), T4 (Metric)
- **文件**:
  - `src/components/data/dittogrid/ditto-grid.tsx` (主封装组件)
  - `src/components/data/dittogrid/theme.ts` (暗色主题配置)
  - `src/components/data/dittogrid/cells/sparkline-cell.tsx`
  - `src/components/data/dittogrid/cells/status-badge-cell.tsx`
  - `src/components/data/dittogrid/cells/trend-cell.tsx`
  - `src/components/data/dittogrid/cells/numeric-cell.tsx`
  - `src/components/data/dittogrid/ditto-grid.test.tsx`
  - `src/components/data/dittogrid/index.ts`
- **新增依赖**: `ag-grid-community` v35
- **验收**:
  - [ ] `<DittoGrid>` 接受 columnDefs + rowData，渲染 AG Grid 表格
  - [ ] 暗色主题：backgroundColor / foregroundColor / borderColor / headerBackgroundColor / rowHoverColor 全部映射 Design Token CSS 变量
  - [ ] 默认列定义：numeric 列右对齐 + JetBrains Mono 字体 + `font-feature-settings: 'tnum' 1`
  - [ ] SparklineCell：接受 data/color/gradient props，渲染内嵌 SVG sparkline
  - [ ] StatusBadgeCell：接受 label/variant props，渲染 StatusBadge 组件
  - [ ] TrendCell：接受 value (正数=up/负数=down/零=flat) props，渲染颜色 + 箭头
  - [ ] NumericCell：接受 value props，渲染右对齐千分位格式数字
  - [ ] 表头样式：sticky + `--surface-strip` 背景 + 12px 字号 + uppercase + tertiary 色
  - [ ] 行 hover：`--interaction-hover-subtle-bg`
  - [ ] 行 selected：`--interaction-selected-bg` + 左侧 3px brand-accent box-shadow
  - [ ] CSV 快导出按钮
  - [ ] `bun add ag-grid-community`
  - [ ] barrel export

---

## 文件变更总览

### 新增文件（17 个）

```
src/components/
├── status/
│   ├── index.ts
│   ├── status-dot/
│   │   ├── index.ts
│   │   ├── status-dot.tsx
│   │   └── status-dot.test.tsx
│   └── status-badge/
│       ├── index.ts
│       ├── status-badge.tsx
│       └── status-badge.test.tsx
├── data/
│   ├── index.ts
│   ├── sparkline/
│   │   ├── index.ts
│   │   ├── sparkline.tsx
│   │   └── sparkline.test.tsx
│   ├── metric/
│   │   ├── index.ts
│   │   ├── metric.tsx
│   │   └── metric.test.tsx
│   ├── skeleton/
│   │   ├── index.ts
│   │   ├── loading-skeleton.tsx
│   │   └── loading-skeleton.test.tsx
│   └── dittogrid/
│       ├── index.ts
│       ├── ditto-grid.tsx
│       ├── theme.ts
│       ├── ditto-grid.test.tsx
│       └── cells/
│           ├── sparkline-cell.tsx
│           ├── status-badge-cell.tsx
│           ├── trend-cell.tsx
│           └── numeric-cell.tsx
└── lib/
    ├── error-boundary.tsx
    ├── error-boundary.test.tsx
    ├── stale-indicator.tsx
    └── stale-indicator.test.tsx
```

### 新增依赖（2 个）

```bash
bun add ag-grid-community react-error-boundary
```

---

## 执行顺序

```
并行启动 ──────────────────────────────────
│ T1 StatusDot          │ T3 Sparkline     │ T5 Skeleton       │
│ (S, ~30min)           │ (M, ~1h)          │ (M, ~1h)           │
└───────┬───────────────┴───────┬──────────┴────────┬──────────┘
        ↓                       ↓                    ↓
   T2 StatusBadge          T4 Metric            T6 ErrorState
   (M, ~1h)                (M, ~1.5h)           + StaleIndicator
        │                       │               (M, ~1h)
        │                       │                    │
        └───────────┬───────────┘                    │
                    ↓                                │
              T7 DittoGrid ◄─────────────────────────┘
              (L, ~3h)
                    ↓
              Phase 1 验收
```

---

## Phase 验收标准

1. `bun run check` 全绿（lint + type + test）
2. 每个组件至少 3 个测试用例（渲染 / 变体 / 边界）
3. 所有样式使用 CSS 变量，无硬编码像素值
4. DittoGrid 暗色主题与原型 data-table 视觉一致
5. barrel export 链路通畅：`import { Metric, Sparkline, StatusBadge, StatusDot, DittoGrid, LoadingSkeleton } from "@/components/data"`
