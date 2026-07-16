# 共享业务组件分层建设设计

> 日期: 2026-04-08
> 状态: Approved
> 范围: 将 17 个 HTML 原型的共享业务组件按严格分层建设，为逐页填充打下基础
> 前置: Shell-First 原型落地（Tier 1 已完成）

---

## 1. 目标

将 Ditto 原型（17 页，均分 9.21/10）中的共享业务组件按严格分层建设：

- **分层建设**：先建共享组件，再逐页填充内容，最大化复用
- **像素级还原**：对照原型 HTML/CSS 源文件实现
- **Design Token 1:1 映射**：所有尺寸、颜色、间距使用 CSS 变量
- **TDD 驱动**：每个组件先写测试再实现

---

## 2. 分层架构

```
Tier 1  ✅ 已完成 — Shell 层（AppShell / Rail / Header / 6 Layouts / NoiseLayer）
Tier 2  🔲 核心数据展示 — Metric / Sparkline / DittoGrid / Boundary 系统
Tier 2.5 🔲 基础原子 — StatusBadge / StatusDot
Tier 3  🔲 状态与指标 — ScopeStrip / ConfidenceBar / AlertRow / Overlay
Tier 4  🔲 域组件 — Decision Banner / Market Card / Context Section / Filter Controls / Timeline
```

### 2.1 关键技术决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 数据表格 | AG Grid Community v35 + DittoGrid 封装 | 技术选型文档冻结，禁止先用轻量 table 再迁移 |
| 图表三轨制 | SVG Sparkline / ECharts / Lightweight Charts | 与技术选型文档完全对齐 |
| 四态处理 | React Boundary（Suspense + ErrorBoundary + StaleIndicator） | 业界最佳实践，React 19 Suspense 稳定 |
| 跨 Tier 依赖 | StatusBadge/StatusDot 提前为 Tier 2.5 | DittoGrid 和 Metric 的硬依赖 |
| Chat 系统 | Vercel AI SDK + 流式输出 + UI 绘图 | 后续专项讨论技术方案 |

### 2.2 技术依赖关系

```
Sparkline ──→ Metric ──→ DittoGrid (cell renderer)
                     ──→ Decision Banner (Tier 4)

StatusBadge ──→ DittoGrid (cell renderer)
StatusDot  ──→ ScopeStrip, AlertRow, HealthIndicator

Boundary 系统 ──→ 所有页面级 Layout
```

---

## 3. 目录结构

```
src/
├── components/
│   ├── ui/              # shadcn 基础（已有 Button/Badge/Tabs/Collapsible/Separator）
│   ├── data/            # Tier 2: 数据展示组件
│   │   ├── metric/
│   │   ├── sparkline/
│   │   ├── dittogrid/
│   │   └── skeleton/
│   ├── status/          # Tier 2.5: 状态原子
│   │   ├── status-badge/
│   │   └── status-dot/
│   ├── indicator/       # Tier 3: 指标组件
│   │   ├── scope-strip/
│   │   ├── confidence-bar/
│   │   ├── alert-row/
│   │   └── overlay/
│   └── domain/          # Tier 4: 域组件
│       ├── decision-banner/
│       ├── market-card/
│       ├── context-section/
│       ├── filter-controls/
│       ├── timeline/
│       └── chat/        # 后续专项
├── features/
│   ├── shell/           # 已完成
│   └── navigation/      # 已完成
└── lib/
    ├── error-boundary.tsx   # Tier 2: ErrorBoundary 配置
    └── stale-indicator.tsx  # Tier 2: Stale 指示器
```

---

## 4. Tier 2 — 核心数据展示组件

### 4.1 Sparkline（SVG 迷你折线图）

纯 SVG 实现，无外部依赖，~2KB。

**Props**：
```typescript
interface SparklineProps {
  data: number[]           // 数据点序列
  width?: number           // 默认 32
  height?: number          // 默认 12
  color?: 'up' | 'down' | 'neutral'  // 语义色，映射到 token
  gradient?: boolean       // 是否渐变填充，默认 true
  strokeWidth?: number     // 默认 1.5
  animate?: boolean        // 入场动画，默认 true
}
```

**使用场景**：Metric 卡片内嵌、Table 单元格、Decision Banner PnL、Market Card 折线。

**实现要点**：
- `<path>` 绘制折线 + 可选渐变填充 `<linearGradient>`
- `color` 映射到 `--color-market-up` / `--color-market-down` / `--color-foreground-muted`
- 入场动画用 CSS `stroke-dasharray` + `stroke-dashoffset` transition

### 4.2 Metric（KPI 指标展示）

原型中 284+ 实例，最高频组件。3 种变体：

| 变体 | 结构 | 使用场景 |
|------|------|---------|
| `Standard` | label + value + sub（可选 sparkline） | 面板内 KPI |
| `Strip` | label + value（紧凑单行） | ScopeStrip / RiskStrip / PulseStrip |
| `Equity` | 大号 value + pct + sub-items | Decision Banner PnL |

**Props**：
```typescript
interface MetricProps {
  label: string
  value: string | number
  sub?: string              // 副文本
  trend?: 'up' | 'down' | 'flat'  // 趋势箭头
  sparkline?: SparklineProps  // 可选内嵌 sparkline
  variant?: 'standard' | 'strip' | 'equity'
  size?: 'sm' | 'md' | 'lg'
}
```

**样式映射**：
- `label` → `text-[var(--font-size-12)] text-[var(--foreground-tertiary)]`
- `value` → 按 size 映射 `--font-size-20/28/36`
- `trend` → CSS 三角箭头 + 语义色

### 4.3 DittoGrid（AG Grid 封装层）

按技术选型文档 3.3 节封装，不直接暴露 `<AgGridReact />`。

**首期封装范围**：
```
DittoGrid
├── 默认列定义（数值/百分比/时间格式化 + Token 暗色主题）
├── 自定义单元格渲染器
│   ├── SparklineCell    — 内嵌 SVG sparkline
│   ├── StatusBadgeCell  — 状态标签
│   ├── TrendCell        — 涨跌箭头 + 颜色
│   └── NumericCell      — 右对齐 + 千分位格式
├── 暗色主题（映射 Design Token → AG Grid theme）
└── CSV 快导出
```

**首期不做**（后续逐页阶段补）：
- Infinite Row Model（需后端 API）
- 筛选状态持久化
- 列状态保存/恢复
- XLSX 导出触发
- 权限开关

**暗色主题映射**：
```typescript
backgroundColor: 'var(--surface-1)',
foregroundColor: 'var(--foreground-primary)',
borderColor: 'var(--border-subtle)',
headerBackgroundColor: 'var(--surface-2)',
rowHoverColor: 'var(--surface-2)',
```

### 4.4 Boundary 系统（四态处理）

**三层架构**：

| 层 | 组件 | 职责 |
|---|------|------|
| Loading | `<Suspense fallback={<Skeleton />}>` | 骨架屏 |
| Error | `<ErrorBoundary>` (react-error-boundary) | 错误提示 + 重试 |
| Stale | `<StaleIndicator />` | 顶部淡蓝条 |

**LoadingSkeleton**：
```typescript
interface SkeletonProps {
  variant: 'panel' | 'table' | 'card' | 'metric' | 'chart'
  lines?: number           // panel 模式的行数
  rows?: number            // table 模式的行数
  columns?: number         // table 模式的列数
}
```

- `panel`：模拟 panel-header + n 行 shimmer 条
- `table`：模拟表头 + n 行 m 列 shimmer 格
- `card`：模拟卡片标题 + 内容区
- `metric`：模拟 label + value 的 shimmer
- `chart`：模拟图表区域的 shimmer 块

**ErrorState**：
```typescript
interface ErrorStateProps {
  title?: string           // 默认 "加载失败"
  description?: string
  onRetry?: () => void     // 重试回调
}
```

**StaleIndicator**：TanStack Query `isFetching` 为 true 时显示顶部 2px 渐变条（brand-accent 低透明度），数据更新后自动消失。

---

## 5. Tier 2.5 — 基础状态原子

### 5.1 StatusBadge（状态标签）

原型中 204+ 实例，跨 16 页。dot + label 结构。

**Props**：
```typescript
interface StatusBadgeProps {
  label: string
  variant: StatusBadgeVariant
  size?: 'sm' | 'md'
}

type StatusBadgeVariant =
  | 'default'
  | 'healthy' | 'degraded' | 'warning' | 'critical'
  | 'live' | 'idle' | 'error'
  | 'trade' | 'risk' | 'research' | 'platform' | 'data' | 'priority'
  | 'regime-on' | 'regime-off' | 'regime-mixed'
  | 'active' | 'inactive'
```

**样式映射**：
- dot 颜色 → `--status-led-{variant}`（L4 data-viz token）
- 背景色 → dot 颜色 10% 透明度
- label → `text-[var(--font-size-12)]`

**原型类名映射**：

| 原型 class | StatusBadge variant |
|---|---|
| `queue-item-tag trade` | `trade` |
| `regime-tag on` | `regime-on` |
| `market-card-regime mixed` | `regime-mixed` |
| `source-item-badge warn` | `warning` |
| `status-dot live` | `live` |

### 5.2 StatusDot（状态指示灯）

原型中 155+ 实例。StatusBadge 的无文字版。

**Props**：
```typescript
interface StatusDotProps {
  variant: StatusDotVariant
  size?: 'sm' | 'md' | 'lg'  // 6px / 8px / 10px
  pulse?: boolean              // live 状态时带脉冲动画
}

type StatusDotVariant =
  | 'healthy' | 'degraded' | 'warning' | 'critical'
  | 'live' | 'idle' | 'error'
  | 'info'
```

**样式映射**：
- 颜色 → 复用 `--status-led-*` token
- `pulse` → CSS `@keyframes pulse` 缩放 + 透明度
- 尺寸 → `sm: 6px, md: 8px, lg: 10px`

### 5.3 与 shadcn Badge 的关系

- **shadcn Badge** → 通用 UI 标签（"New"、"Pro"），纯装饰/分类
- **StatusBadge** → 带业务语义的状态指示器，颜色映射到领域 token
- 两者不冲突，StatusBadge 独立实现

---

## 6. Tier 3 — 状态与指标组件

### 6.1 ScopeStrip（页面级状态摘要条）

7 个页面使用，位于 Header 下方。通用结构 + Metric.Strip 子项组合。

**Props**：
```typescript
interface ScopeStripProps {
  children: React.ReactNode   // Metric.Strip 子项
  divider?: boolean           // 分隔符，默认 true
}
```

**各页面内容**：

| 页面 | Metric 数量 |
|------|------------|
| Cross-Market | 6（市场体制 + 指数 + 波动率） |
| Trading Overview | 6（总权益 + 日盈亏 + 持仓数 + 胜率） |
| Risk Center | 8（VaR + 最大回撤 + 集中度 + 杠杆） |
| Regime Monitor | 7（体制状态 + 转换概率 + 持续时间） |
| Signals Inbox | 4（信号数 + 待执行 + 已过期） |
| Research | 4（研究报告数 + 活跃因子） |

**样式**：`bg-[var(--surface-0)] border-b border-[var(--border-subtle)]` + `px-[var(--space-16)]`

### 6.2 ConfidenceBar（置信度条）

30+ 实例，用于 AI 判断置信度、信号强度、体制概率。

**Props**：
```typescript
interface ConfidenceBarProps {
  value: number             // 0-100
  max?: number              // 默认 100
  color?: ConfidenceColor
  size?: 'sm' | 'md'       // 高度 4px / 6px
  showLabel?: boolean       // 是否显示百分比文字
  segments?: Segment[]      // 可选：分段堆叠
}

type ConfidenceColor = 'brand' | 'success' | 'warning' | 'danger' | 'neutral'

interface Segment {
  value: number
  color: ConfidenceColor
  label?: string
}
```

**两种模式**：单值 + 分段堆叠。

### 6.3 AlertRow（告警行）

4 个页面使用，60+ 实例。

**Props**：
```typescript
interface AlertRowProps {
  severity: 'critical' | 'warning' | 'info'
  title: string
  time?: string
  onClick?: () => void
}
```

内部复用 StatusDot。

### 6.4 Overlay（弹层系统）

16 页共 60 个实例，两种形态：

**Sheet（居中模态框）**：
```typescript
interface SheetProps {
  open: boolean
  onClose: () => void
  title: string
  children: React.ReactNode
  actions?: React.ReactNode
  size?: 'sm' | 'md' | 'lg'
}
```

**Drawer（右侧抽屉）**：
```typescript
interface DrawerProps {
  open: boolean
  onClose: () => void
  title: string
  children: React.ReactNode
  width?: number              // 默认 var(--shell-detail-width) = 340px
}
```

基于 Radix Dialog（shadcn 体系），扩展 Sheet + 新增 Drawer。

---

## 7. Tier 4 — 域组件

### 7.1 ContextSection（侧边栏可折叠面板）

7 个页面使用，90+ 实例。基于 shadcn Collapsible 封装。

**Props**：
```typescript
interface ContextSectionProps {
  title: string
  count?: number
  defaultOpen?: boolean      // 默认 true
  action?: React.ReactNode
  children: React.ReactNode
}
```

### 7.2 FilterControls（筛选控件组）

9 个页面使用，132+ 实例。两种形态：

**FilterChip**（水平标签组）：
```typescript
interface FilterChipProps {
  label: string
  active?: boolean
  count?: number
  onClick?: () => void
}
```

**FilterSelect**（下拉筛选）：
```typescript
interface FilterSelectProps {
  label: string
  options: { label: string; value: string }[]
  value?: string
  onChange?: (value: string) => void
}
```

### 7.3 Timeline（时间线）

5 个页面使用。通用骨架 + 场景变体：

**Props**：
```typescript
interface TimelineProps {
  items: TimelineItem[]
  variant?: 'default' | 'status' | 'regime' | 'activity'
}

interface TimelineItem {
  id: string
  marker: 'dot' | 'event' | 'earnings' | 'filing' | 'completed' | 'failed'
  title: string
  description?: string
  time: string
  content?: React.ReactNode
}
```

**首期实现 `default` 和 `activity`**，`status` 和 `regime` 逐页阶段按需补充。

### 7.4 Decision Banner（决策横幅）

2 个页面使用（Home / Trading Overview），由 Tier 2/2.5 组件组合。

**Props**：
```typescript
interface DecisionBannerProps {
  primary: {
    equity: MetricProps          // variant="equity"
    pnl: MetricProps             // variant="equity" + sparkline
  }
  judgment: {
    regime: StatusBadgeProps
    aiText: string
    kpis: MetricProps[]          // variant="strip"
  }
  actions: {
    label: string
    variant: 'primary' | 'secondary' | 'ghost'
    onClick?: () => void
  }[]
}
```

### 7.5 Market Card（市场卡片）

仅 Cross-Market 页面，12 个实例。由 Tier 2/2.5 组件组合。

**Props**：
```typescript
interface MarketCardProps {
  name: string
  regime: 'on' | 'off' | 'mixed'
  index: string
  change: number
  judgment: string
  sparkline?: SparklineProps
  onClick?: () => void
}
```

### 7.6 Chat（对话系统）— 待定

**方向**：Vercel AI SDK + 流式输出 + UI 绘图。

**状态**：需后续专项讨论技术方案，不在共享组件阶段建设。

---

## 8. 实施计划

### 8.1 Phase 1 — Tier 2 + 2.5

```
Sparkline ──→ Metric ──┐
StatusDot → StatusBadge │──→ DittoGrid
Boundary 系统 ──────────┘
```

**新增依赖**：`ag-grid-community` v35、`react-error-boundary`

### 8.2 Phase 2 — Tier 3

```
ConfidenceBar + AlertRow + ScopeStrip + Overlay
```

### 8.3 Phase 3 — Tier 4

```
ContextSection → FilterControls → Timeline → DecisionBanner → MarketCard
```

### 8.4 新增依赖总表

| 依赖 | 用途 | Phase |
|------|------|-------|
| `ag-grid-community` v35 | DittoGrid 底层 | Phase 1 |
| `react-error-boundary` | Boundary 系统 | Phase 1 |
| `@vercel/ai-sdk` | Chat 流式交互（预留） | Phase 3+ |
| `echarts` + `echarts-for-react` | 通用图表 | 逐页阶段 |
| `lightweight-charts` | K 线图表 | 逐页阶段 |

---

## 9. 验收标准

每个 Phase 完成后：

1. **`bun run check` 全绿** — lint + type + test
2. **测试覆盖** — 每个组件至少：渲染测试、变体切换测试、边界值测试
3. **视觉对照** — 浏览器中打开原型 HTML + React 实现，Grid 结构和尺寸一致
4. **Token 对齐** — 所有颜色/尺寸/间距使用 CSS 变量，无硬编码值
5. **可组合性** — Tier 4 组件能正确使用 Tier 2/2.5 组件组合

---

## 10. 完整组件清单

| Tier | 组件 | 类型 | 原型实例数 | 复用页数 |
|------|------|------|-----------|---------|
| 1 ✅ | AppShell / Rail / Header / NoiseLayer | Shell | — | 16 |
| 1 ✅ | 6 Shell Layouts | Layout | — | 16 |
| 2 | Sparkline | 数据展示 | 70+ | 9 |
| 2 | Metric | 数据展示 | 284+ | 11 |
| 2 | DittoGrid | 数据展示 | 53+ | 12 |
| 2 | LoadingSkeleton | 状态 | — | 16 |
| 2 | ErrorState | 状态 | — | 16 |
| 2 | StaleIndicator | 状态 | — | 16 |
| 2.5 | StatusDot | 状态原子 | 155+ | 15 |
| 2.5 | StatusBadge | 状态原子 | 204+ | 16 |
| 3 | ScopeStrip | 指标 | 7 页 | 7 |
| 3 | ConfidenceBar | 指标 | 30+ | 7 |
| 3 | AlertRow | 指标 | 60+ | 4 |
| 3 | Overlay (Sheet + Drawer) | 交互 | 60+ | 16 |
| 4 | ContextSection | 域组件 | 90+ | 7 |
| 4 | FilterControls | 域组件 | 132+ | 9 |
| 4 | Timeline | 域组件 | 5 页 | 5 |
| 4 | DecisionBanner | 域组件 | 2 | 2 |
| 4 | MarketCard | 域组件 | 12 | 1 |
| 4 | Chat | 域组件 | 1 | 1 |

**总计**：19 个新组件（不含已完成 6+5），覆盖原型 95%+ 的 UI 模式。
