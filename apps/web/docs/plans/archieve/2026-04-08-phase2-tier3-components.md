# Phase 2: 共享业务组件 Tier 3

## 概述
- Sprint: Phase 2 | 共享组件分层建设
- 创建: 2026-04-08
- 前置: [2026-04-08-phase1-shared-components.md](./2026-04-08-phase1-shared-components.md) ✅ 完成（22 files, 280 tests）
- 设计: [2026-04-08-shared-component-layer-design.md](./2026-04-08-shared-component-layer-design.md) §6
- 范围: ScopeStrip / ConfidenceBar / AlertRow / Overlay（Sheet + Drawer）

## 技术方案

### 关键决策
| 决策 | 选择 | 理由 |
|------|------|------|
| ScopeStrip | 通用容器 + compose | 子项由页面用 Metric.Strip/StatusBadge 等组合，灵活复用 Phase 1 |
| ConfidenceBar | CVA 单值 + 分段双模式 | 覆盖原型 30+ 实例的两种使用模式 |
| AlertRow | 简洁行组件，内部复用 StatusDot | 60+ 实例统一结构 |
| Overlay | 基于 shadcn Dialog + Sheet | Radix 无障碍 + 动画 + Design Token 暗色主题 |
| 新增 shadcn | Dialog + Sheet | Overlay 的 Radix 基础 |
| Drawer | 自行封装（Radix SlideIn） | shadcn 无 Drawer 组件，基于 Dialog primitives 封装 |

### 执行依赖链
```
T1 AlertRow ──────────────────────────┐  (依赖 StatusDot，已有)
T2 ConfidenceBar ─────────────────────┤  (无依赖)
T3 ScopeStrip ────────────────────────┤  (无依赖)
T4 Overlay (Dialog + Sheet + Drawer) ─┘  (需先安装 shadcn Dialog/Sheet)
```

T1/T2/T3 可并行，T4 独立。

---

## 任务清单

### T1: AlertRow 告警行 `[S]`
- **复杂度**: S | 单文件 <60 行
- **依赖**: StatusDot（Phase 1 已完成）
- **文件**:
  - `src/components/indicator/alert-row/alert-row.tsx`
  - `src/components/indicator/alert-row/alert-row.test.tsx`
  - `src/components/indicator/alert-row/index.ts`
- **原型参考**: `shared/layout-base.css` L1116-1152, `page-home.html` L1301-1320
- **Props**:
  ```typescript
  interface AlertRowProps extends React.HTMLAttributes<HTMLDivElement> {
    readonly severity: 'critical' | 'warning' | 'info'
    readonly title: string
    readonly time?: string
    readonly onClick?: () => void
  }
  ```
- **样式映射**:
  - 容器: `flex items-center gap-[var(--space-8)] py-[var(--density-cell-padding-y)] px-[var(--space-12)] border-b border-(--color-border-subtle) last:border-b-0`
  - Severity dot: 复用 `StatusDot`，critical→critical, warning→degraded, info→info
  - critical dot: 默认 pulse 动画（`pulse={true}`）
  - Title: `text-[var(--font-size-12)] text-(--color-foreground-primary) flex-1 min-w-0 truncate`
  - Time: `font-data text-[var(--font-size-12)] text-(--color-foreground-tertiary) tabular-nums shrink-0`
  - Hover: `transition-colors duration-120 hover:bg-(--color-surface-2)`
  - Cursor: `onClick` 存在时 `cursor-pointer`
- **验收**:
  - [ ] 渲染 severity dot + title + 可选 time
  - [ ] 支持 critical / warning / info 三种 severity
  - [ ] critical 级别 dot 自动 pulse 动画
  - [ ] 非最后子元素显示底部边框
  - [ ] title 文本超长时 truncate
  - [ ] onClick 存在时 hover 显示背景 + cursor-pointer
  - [ ] barrel export

### T2: ConfidenceBar 置信度条 `[S]`
- **复杂度**: S | 单文件 <80 行
- **依赖**: 无
- **文件**:
  - `src/components/indicator/confidence-bar/confidence-bar.tsx`
  - `src/components/indicator/confidence-bar/confidence-bar.test.tsx`
  - `src/components/indicator/confidence-bar/index.ts`
- **原型参考**: `shared/layout-base.css` L2095-2113（compact）、L2923-2940（progress）
- **Props**:
  ```typescript
  interface ConfidenceBarProps extends React.HTMLAttributes<HTMLDivElement> {
    readonly value: number             // 0-100
    readonly max?: number              // 默认 100
    readonly color?: ConfidenceColor   // 默认 'neutral'
    readonly size?: 'sm' | 'md'       // 高度 4px / 6px
    readonly showLabel?: boolean       // 是否显示百分比文字
    readonly segments?: readonly Segment[]
  }

  type ConfidenceColor = 'brand' | 'success' | 'warning' | 'danger' | 'neutral'

  interface Segment {
    readonly value: number
    readonly color: ConfidenceColor
    readonly label?: string
  }
  ```
- **样式映射**:
  - Track: `h-1 size=sm / h-1.5 size=md, bg-(--color-border-subtle) rounded-full overflow-hidden`
  - Fill 单值: `h-full rounded-full transition-[width] duration-200 ease-[var(--ease-default)]`
  - Color 映射: brand→`--color-brand-accent`, success→`--color-status-led-healthy`, warning→`--color-status-led-warning`, danger→`--color-status-led-critical`, neutral→`--color-foreground-secondary`
  - Label: `font-data text-[var(--font-size-10)] text-(--color-foreground-tertiary) tabular-nums`
  - 分段模式: fill 用 `flex` + 各 segment 按百分比分配 `width`
- **验收**:
  - [ ] 单值模式：渲染 track + fill，fill 宽度 = (value/max)*100%
  - [ ] 分段模式：渲染 track + 多段 fill，各段按 value 占比
  - [ ] 支持 5 种 color
  - [ ] 支持 sm(4px) / md(6px) 两种尺寸
  - [ ] showLabel=true 时右侧显示 "XX%" 文字
  - [ ] value=0 时 fill 宽度为 0，不报错
  - [ ] value > max 时 clamp 到 100%
  - [ ] fill 宽度变化有 CSS transition
  - [ ] barrel export

### T3: ScopeStrip 页面级状态摘要条 `[S]`
- **复杂度**: S | 单文件 <50 行
- **依赖**: 无（子项 compose 用 Phase 1 组件，但不直接依赖）
- **文件**:
  - `src/components/indicator/scope-strip/scope-strip.tsx`
  - `src/components/indicator/scope-strip/scope-strip.test.tsx`
  - `src/components/indicator/scope-strip/index.ts`
- **原型参考**: `shared/layout-base.css` L2665-2676
- **Props**:
  ```typescript
  interface ScopeStripProps extends React.HTMLAttributes<HTMLDivElement> {
    readonly children: React.ReactNode
    readonly role?: string            // 默认 'status'
    readonly ariaLabel?: string
  }
  ```
- **样式映射**:
  - 容器: `flex items-center gap-[var(--space-12)] bg-(--color-surface-1) border-b border-(--color-border-subtle) h-[var(--density-strip-height)] px-[var(--density-gutter)] overflow-x-auto`
  - 数据属性: `data-slot="scope-strip"`
- **验收**:
  - [ ] 渲染 flex 容器，子项水平排列
  - [ ] 使用 Design Token 背景、边框、间距
  - [ ] 支持 role 和 ariaLabel（默认 role="status"）
  - [ ] 内容溢出时水平滚动
  - [ ] barrel export

### T4: Overlay 弹层系统（Sheet + Drawer）`[M]`
- **复杂度**: M | 3 文件 + 2 shadcn 组件安装，~150 行
- **依赖**: 需先安装 shadcn Dialog + Sheet
- **新增依赖**: `@radix-ui/react-dialog`（通过 shadcn 安装）
- **文件**:
  - `src/components/ui/dialog.tsx`（shadcn 生成）
  - `src/components/ui/sheet.tsx`（shadcn 生成）
  - `src/components/indicator/overlay/drawer.tsx`
  - `src/components/indicator/overlay/overlay.ts`（导出入口）
  - `src/components/indicator/overlay/drawer.test.tsx`
  - `src/components/indicator/overlay/index.ts`
- **原型参考**: `shared/prototype-toggles.css` L335-385
- **shadcn Dialog/Sheet**: 安装后映射 Design Token 暗色主题
- **Drawer Props**:
  ```typescript
  interface DrawerProps {
    readonly open: boolean
    readonly onClose: () => void
    readonly title: string
    readonly children: React.ReactNode
    readonly width?: string          // 默认 '340px'
    readonly className?: string
  }
  ```
- **Drawer 样式映射**:
  - 基于 Radix Dialog primitives，右侧滑入
  - 容器: `bg-(--color-surface-3) border-l border-(--color-border-subtle)`
  - 宽度: 默认 340px
  - Header: `flex items-center justify-between pb-[var(--space-12)] border-b border-(--color-border-subtle) mb-[var(--space-12)]`
  - Title: `text-[var(--font-size-14)] font-semibold text-(--color-foreground-primary)`
  - Body: `text-[var(--font-size-12)] text-(--color-foreground-secondary) leading-relaxed`
  - 滑入动画: Radix Dialog `SlideIn` from right + `Overlay` fade
- **验收**:
  - [ ] Dialog 组件安装完成，暗色主题 Token 对齐
  - [ ] Sheet 组件安装完成，暗色主题 Token 对齐
  - [ ] Drawer：接受 open/onClose/title/children props
  - [ ] Drawer：open=true 时从右侧滑入，open=false 时关闭
  - [ ] Drawer：点击 backdrop 或关闭按钮触发 onClose
  - [ ] Drawer：Escape 键触发 onClose
  - [ ] Drawer：标题栏显示 title + 关闭按钮
  - [ ] Drawer：body 区域可滚动
  - [ ] Dialog/Sheet: data-slot 属性正确
  - [ ] barrel export

---

## 目录结构（新增）

```
src/components/
├── ui/
│   ├── dialog.tsx          # shadcn Dialog（新增）
│   ├── sheet.tsx           # shadcn Sheet（新增）
│   └── ...（已有 button/badge/tabs/collapsible/separator）
├── indicator/              # Tier 3 目录（新建）
│   ├── index.ts            # barrel export
│   ├── alert-row/
│   │   ├── index.ts
│   │   ├── alert-row.tsx
│   │   └── alert-row.test.tsx
│   ├── confidence-bar/
│   │   ├── index.ts
│   │   ├── confidence-bar.tsx
│   │   └── confidence-bar.test.tsx
│   ├── scope-strip/
│   │   ├── index.ts
│   │   ├── scope-strip.tsx
│   │   └── scope-strip.test.tsx
│   └── overlay/
│       ├── index.ts
│       ├── drawer.tsx
│       └── drawer.test.tsx
```

---

## 新增依赖

```bash
bunx shadcn@latest add dialog sheet
# 这会自动安装 @radix-ui/react-dialog
```

---

## 执行顺序

```
并行启动 ───────────────────────────────────
│ T1 AlertRow        │ T2 ConfidenceBar    │ T3 ScopeStrip       │
│ (S)                │ (S)                 │ (S)                 │
└─────────┬──────────┴─────────┬───────────┴─────────┬──────────┘
          │                    │                     │
          └──────────┬─────────┴─────────────────────┘
                     ↓
              T4 Overlay（需先安装 shadcn Dialog/Sheet）
              (M)
                     ↓
              Phase 2 验收
```

---

## Phase 验收标准

1. `bun run check` 全绿（lint + type + test）
2. 每个组件至少 3 个测试用例（渲染 / 变体 / 边界）
3. 所有样式使用 CSS 变量（Design Token），无硬编码像素值
4. barrel export 链路通畅：
   ```typescript
   import { ScopeStrip, ConfidenceBar, AlertRow, Drawer } from "@/components/indicator"
   import { Dialog, Sheet } from "@/components/ui/dialog"
   import { Sheet as DittoSheet } from "@/components/ui/sheet"
   ```
5. Dialog/Sheet 暗色主题与 Ditto Design Token 对齐
