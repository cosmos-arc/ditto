# Ditto Design Token 稳定化规范

> **版本**: v1.3 (R2.5 — Component layer + Audit complete)
> **日期**: 2026-03-31
> **状态**: Active
> **上游**: [14 Token Naming & Layering](./14_ditto_token_naming_layering_spec.md)
> **下游**: 所有原型页面、Component Spec

---

## 1. 概述

Token Stabilization R1 是 Ditto Design Token 体系从"设计阶段"走向"工程落地"的第一轮稳定化行动。其核心目标：

1. **消除野生 Token** — 清理未定义、已废弃、拼写错误的 CSS 变量引用，确保每个 `var(--*)` 都有对应的 `:root` 定义。
2. **固化 Token 层架构** — 将上游规范 [14_ditto_token_naming_layering_spec.md](./14_ditto_token_naming_layering_spec.md) 中定义的 9 层体系落实为具体的 CSS 文件与变量清单。
3. **建立基线质量度量** — 通过审计当前代码库中 hardcoded 值、inline styles、未定义变量等anti-pattern，建立可追踪的质量基线。
4. **锁定稳定 API** — 明确哪些 token 已稳定（不应随意变更）、哪些暂未实现（标记为 debt），为后续迭代提供清晰的演进路线。

**范围**：仅涉及 CSS Custom Properties 层面的 Token 定义与引用规范，不涉及组件实现或 Tailwind utility class 的使用约束（后者在 Component Spec 中定义）。

---

## 2. Token 层架构 (9-Layer)

基于上游规范 §3 定义的 9 层结构，R1 阶段的实际落地状态如下：

| # | 层名 | 职责 | 对应 CSS 文件 | Token 数量 | 依赖 | R1 状态 |
|---|------|------|--------------|-----------|------|--------|
| 1 | **Foundation** | 物理原语：中性色、品牌色、功能色、字号、字重、字体、间距、圆角、动画、色觉辅助符号 | `tokens-base.css` | 49 | 无 | ✅ 已稳定 |
| 2 | **Semantic Surface** | 界面表面语义：背景层级、文本层级（含 data-stale）、边框、品牌强调、图标、滚动条、代码/等宽、分隔线、Overlay（白色透明度）、Frosted Glass、Domain 签名色 | `tokens-semantic.css` | 42 + 24 (domain) | L1 | ✅ 已稳定 |
| 2b | **Atmosphere** | 亚感知级背景氛围：色温渐变、面板呼吸动画（运行时由 JS hook 注入） | `tokens-atmosphere.css` | 5 | L2 | ✅ Living Graphite |
| 3 | **Shell** | 页面壳层布局：rail/header/sidebar/detail/context-bar/status-bar 尺寸 + per-shell overrides | `tokens-shell.css` | 18 | L1, L2 | ✅ 已稳定 |
| 4 | **Data Visualization** | 图表/热力图/sparkline/数据新鲜度/资产类别色/状态 LED | `tokens-data-viz.css` | 38 | L1-L3 | ✅ 已稳定 |
| 5 | **Component** | UI 组件结构 token：button/badge/card/panel/input/tab/checkbox/status-dot | `tokens-component.css` | 38 | L1, L2, L8 | ✅ 已稳定 |
| 6 | **Interaction** | 交互状态：focus/hover/selected/active/dragging/feedback | `tokens-interaction.css` | 14 | L1, L2 | ✅ 已稳定 |
| 7 | **Domain Semantic** | 业务域状态色：Market/Risk/Execution/System/DataQuality/Model/Agent | `tokens-domain.css` | 50 | L1, L2 | ✅ 已稳定 |
| 8 | **Density** | 密度档位切换：dense/compact/comfortable 三档 | `tokens-density.css` | 14×3 | L1 | ✅ 已稳定 |
| 9 | **Module Pattern** | 模块级轻微偏置 | — | — | L1-L8 | ⚠️ 未提取 |

### 2.1 Layer 1: Foundation — `tokens-base.css`

最底层物理原语，不直接表达业务语义。总计 52 个 token：

| 类别 | Token 数 | 说明 |
|------|---------|------|
| 中性色 neutral | 15 | neutral-0 ~ neutral-950，OKLCH 灰阶 |
| 品牌色 brand | 5 | brand-300 ~ brand-700，品牌强调色 |
| 功能色 functional | 18 | green/red/amber/orange/cyan/purple 各 3 级 (400/500/600) |
| 字号 font-size | 9 | 10/11/12/13/14/16/18/20/24（Edition v1 当前基线） |
| 字重 font-weight | 3 | regular(400)/medium(500)/semibold(600) |
| 字体 font-family | 3 | ui / numeric / mono |
| 间距 spacing | 11 | 2/4/6/8/10/12/16/20/24/32/40 (4pt 体系) |
| 圆角 radius | 6 | 2/4/6/8/12/16 |
| 动画 motion | 5 | duration-fast/normal/slow + easing-standard/emphasis |
| 色觉辅助 indicator | 5 | up-sym/down-sym/flat-sym/critical-sym/warn-sym（CSS 转义字符） |

### 2.2 Layer 2: Semantic Surface — `tokens-semantic.css`

将 Foundation 原语映射为界面表面语义。总计 42 个 token：

| 类别 | Token 数 | 示例变量 |
|------|---------|----------|
| surface | 6 | `--surface-app`, `--surface-panel-base`, `--surface-overlay` 等 |
| text | 7 | `--text-primary`, `--text-secondary`, `--text-tertiary`, `--text-quaternary` 等 |
| text-semantic | 5 | `--text-success`, `--text-warning`, `--text-error` 等 |
| border | 3 | `--border-subtle`, `--border-default`, `--border-strong` |
| border-semantic | 3 | `--border-success`, `--border-warning`, `--border-error` |
| brand-accent | 3 | `--brand-accent-fg`, `--brand-accent-bg`, `--brand-accent-subtle` |
| icon | 3 | `--icon-primary`, `--icon-secondary`, `--icon-muted` |
| scrollbar | 3 | `--scrollbar-track`, `--scrollbar-thumb`, `--scrollbar-thumb-hover` |
| code/mono | 3 | `--code-bg`, `--code-fg`, `--code-border` |
| divider | 2 | `--divider-default`, `--divider-strong` |
| overlay | 7 | `--overlay-2` ~ `--overlay-12`（白色透明度，用于分隔线/背景） |
| frosted glass | 2 | `--surface-frosted`, `--surface-frosted-subtle`（毛玻璃效果） |

### 2.3 Layer 3: Shell — `tokens-shell.css` (R2 提取)

页面壳层布局变量，从 `layout-base.css` 中提取为独立层。总计 18 个 token：

| 类别 | Token 数 | 示例变量 |
|------|---------|----------|
| base shell | 5 | `--shell-rail-width`, `--shell-header-height`, `--shell-sidebar-width`, `--shell-detail-width`, `--shell-rail-collapsed` |
| bar heights | 3 | `--shell-context-bar-height`, `--shell-scope-strip-height`, `--shell-status-bar-height` |
| per-shell overrides | 10 | `--shell-screener-sidebar-width`, `--shell-signals-detail-width` 等 |

`tokens-style.css` 保留少量 prototype-only 结构尺寸覆盖，直到这些值稳定并迁移到 Shell 或 Component 层：`--panel-header-height: 38px`、`--tab-bar-height: 42px`、`--progress-bar-height: 6px`、`--surface-noise-opacity: 0.018`。

### 2.4 Layer 4: Data Visualization — `tokens-data-viz.css` (R2 新增)

量化平台专用数据可视化 token，对标 TradingView paneProperties / Bloomberg Terminal 图表体系。总计 38 个 token：

| 类别 | Token 数 | 示例变量 |
|------|---------|----------|
| data freshness | 6 | `--data-freshness-live`, `--data-freshness-stale`, `--data-freshness-expired` |
| data state | 4 | `--data-state-live-fg`, `--data-state-stale-fg`, `--data-state-disconnected-fg` |
| chart pane | 7 | `--chart-bg`, `--chart-grid`, `--chart-crosshair`, `--chart-axis-text` |
| chart series | 6 | `--chart-series-up`, `--chart-series-up-area`, `--chart-series-down` |
| sparkline | 3 | `--sparkline-width`, `--sparkline-height`, `--sparkline-stroke-width` |
| heatmap | 5 | `--heatmap-1-bg` ~ `--heatmap-5-bg` (sequential scale) |
| asset class | 7 | `--asset-equity`, `--asset-fixed-income`, `--asset-crypto` (Paul Tol bright) |
| status LED | 3 | `--status-connected-color`, `--status-degraded-color`, `--status-error-color` |

### 2.4.1 Layer 4 Legacy — Data View (Component 级)

Table / Context / Visual 三族 component-level token 尚未落地。当前相关值散落在 `layout-base.css` 和各页面组件中。

**预期命名空间**（参考上游规范 §12-§15）：

```
table.analytical.* / table.catalog.* / table.ledger.* / table.ops.*
context.activity.* / context.preview.* / context.detail.* / context.studio.*
visual.main.* / visual.analysis.* / visual.monitor.* / visual.timeline.* / visual.micro.*
```

### 2.5 Layer 5: Component — `tokens-component.css`

UI 组件结构 token，定义 button/badge/card/panel/input/tab/checkbox/status-dot 等组件的尺寸、间距、圆角模式。总计 38 个 token：

> 注意：L4 Data Visualization 是平台级 data viz token（chart grid、freshness、asset class），
> Component 层是具体 UI 组件结构 token（sizing、padding、radius）。
> 两者职责不同，不可合并。

| 类别 | Token 数 | 示例变量 |
|------|---------|----------|
| button | 9 | `--btn-sm-padding-y`, `--btn-padding-x`, `--btn-radius`, `--btn-height` |
| badge/tag/chip | 12 | `--badge-md-padding-y`, `--badge-dot-size`, `--badge-pill-radius` |
| card/panel | 6 | `--card-radius`, `--card-padding`, `--card-border`, `--section-divider` |
| input/select | 7 | `--input-sm-padding-y`, `--input-radius`, `--input-font-size` |
| tab | 6 | `--tab-pill-padding-x`, `--tab-indicator-width`, `--tab-font-size` |
| status indicator | 2 | `--status-dot-size`, `--status-dot-size-lg` |
| checkbox | 3 | `--checkbox-size`, `--checkbox-radius`, `--checkbox-border` |

**模块级角色 token**（action.primary.*, panel.main.* 等）属于 Layer 9 Module Pattern，不在本层定义。

### 2.6 Layer 6: Interaction — `tokens-interaction.css`

统一交互状态 token，不绑定具体组件。总计 14 个 token：

| 类别 | Token 数 | 示例变量 |
|------|---------|----------|
| focus | 2 | `--interaction-focus-ring`, `--interaction-focus-border` |
| hover | 2 | `--interaction-hover-subtle-bg`, `--interaction-hover-strong-bg` |
| selected | 3 | `--interaction-selected-bg`, `--interaction-selected-border`, `--interaction-selected-text` |
| active | 1 | `--interaction-active-press` |
| dragging | 2 | `--interaction-dragging-shadow`, `--interaction-dragging-opacity` |
| feedback-toast | 2 | `--feedback-toast-bg`, `--feedback-toast-border` |
| feedback-banner | 4 | `--feedback-banner-info-*`, `--feedback-banner-warning-*`, `--feedback-banner-error-*`, `--feedback-banner-success-*` |
| feedback-progress | 2 | `--feedback-progress-track`, `--feedback-progress-fill` |

### 2.7 Layer 7: Domain Semantic — `tokens-domain.css`

Ditto 与通用设计系统最核心的差异层。7 个业务域共 50 个 token：

| 域 | Token 数 | 状态枚举 |
|----|---------|----------|
| **Market** | 9 | up / down / flat / strong / weak + fg/bg/subtle |
| **Risk** | 10 | low / medium / high / critical / near-limit / breach |
| **Execution** | 9 | pending / partial / filled / cancelled / rejected |
| **System** | 9 | healthy / degraded / stale / down / recovering |
| **Data Quality** | 7 | fresh / delayed / missing / partial / revised |
| **Model** | 9 | stable / degrading / drifting / invalid / candidate |
| **Agent** | 8 | idle / running / waiting-approval / blocked / failed |

Market 域支持 Region Switching（见 §5）。

### 2.8 Layer 8: Density — `tokens-density.css`

三档密度预设，通过 `[data-density]` 属性切换。详见 §4。

### 2.9 Layer 9: Module Pattern — 未提取

模块级轻微偏置层。允许不同业务模块在统一基础上做微调，但严禁重写主配色或基础密度。

**预期命名空间**（参考上游规范 §30-§31）：

```
module.home.* / module.markets.* / module.research.*
module.trading.* / module.ai.* / module.platform.*
```

---

## 3. Typography Scale

Edition v1 当前采用 9 级字号体系。`--font-size-11` 保留为 tight context token，
仅用于 dense 非交互元数据；交互元素、表格、header、tab、button、primary answer
等 operational selector 的最小字号为 `--font-size-12`。

| Token | Value | Rem | Role | Min Layer |
|-------|-------|-----|------|-----------|
| `--font-size-10` | 0.625rem | 10px | 辅助标签、时间戳、元数据 | L2-L4 |
| `--font-size-11` | 0.6875rem | 11px | Tight contexts、dense 非交互元数据 | L2-L4 |
| `--font-size-12` | 0.75rem | 12px | 交互元素最小字号、数据值、badge | L1-L3 |
| `--font-size-13` | 0.8125rem | 13px | **正文主体** — 全站最常用字号 | All |
| `--font-size-14` | 0.875rem | 14px | 区块标题、section heading、面板标题 | L2-L3 |
| `--font-size-16` | 1rem | 16px | 页面标题、大号区块标题 | L3 |
| `--font-size-18` | 1.125rem | 18px | Sub-heading、宽屏关键摘要 | L3 |
| `--font-size-20` | 1.25rem | 20px | Card title、重点数字模块 | L3 |
| `--font-size-24` | 1.5rem | 24px | 大标题、页面 hero | L3 |

### 字重

| Token | Value | Role |
|-------|-------|------|
| `--font-weight-regular` | 400 | 正文、表格正文、表单输入、tooltip |
| `--font-weight-medium` | 500 | 二级标题、表头、导航项、按钮文字、KPI 标签 |
| `--font-weight-semibold` | 600 | 一级标题、关键模块标题、极少量强调 |

### 字体家族（4-role system）

> **更新**：2026-03-31，从 3 套升级为 4 套
> **完整规范**：[2026-04-01-typography-system-design.md](../../../plans/2026-04-01-typography-system-design.md)

| Token | Value | Role |
|-------|-------|------|
| `--font-family-body` | Inter, Noto Sans SC Variable, Source Han Sans SC, PingFang SC, system-ui | 正文、表单、筛选器、KPI 标签 |
| `--font-family-heading` | Geist Sans, Inter, Noto Sans SC Variable, ... | 页面标题、模块标题、一级导航 |
| `--font-family-data` | Inter, Noto Sans SC Variable, PingFang SC, system-ui | 价格、PnL、收益率 + `tabular-nums slashed-zero` |
| `--font-family-code` | Geist Mono, JetBrains Mono, ui-monospace, ... | 代码编辑器、日志、DSL + `font-variant-ligatures: none` |

### 行高

| Token | Value | Role |
|-------|-------|------|
| `--line-height-compact` | 1.25 | 表格、紧凑列表、导航 |
| `--line-height-normal` | 1.45 | 全局默认（body） |
| `--line-height-relaxed` | 1.60 | 说明文字、长段落、文档型内容 |

### 11px Usage Policy

`--font-size-11` 是当前 9-step scale 的有效 token，但用途受限：

| 场景 | 规则 |
|------|------|
| Dense 非交互元数据 | 可使用 `--font-size-11` |
| 交互元素（button/link/label/role button/switch/tab） | 使用 `--font-size-12` 或更大 |
| 表格、header、tab、button、primary answer selector | 使用 `--font-size-12` 或更大 |
| `cursor: pointer` 的 operational chip / row / target | 使用 `--font-size-12` 或更大 |

28px 不在 Edition v1 当前字号集合；大标题使用 `--font-size-24`。

---

## 4. Density System

三档密度预设，通过 `<html data-density="dense|compact|comfortable">` 切换。默认档位为 `compact`。

### 4.1 dense（高密）

适用于多列数据对比、监控大屏、专业交易员工作台。

| Variable | Value | Px | 说明 |
|----------|-------|----|------|
| `--density-row-height` | 2.125rem | 34px | 数据表格行高 |
| `--density-strip-height` | 2rem | 32px | Summary strip 高度 |
| `--density-header-height` | 1.75rem | 28px | 表头 / 面板头部高度 |
| `--density-input-height` | 1.75rem | 28px | 输入框高度 |
| `--density-action-height` | 1.75rem | 28px | 按钮高度 |
| `--density-chart-header` | 1.75rem | 28px | 图表头部高度 |
| `--density-panel-padding` | `var(--space-8)` | 8px | 面板内边距 |
| `--density-section-gap` | `var(--space-8)` | 8px | 区块间距 |
| `--density-cell-padding-x` | `var(--space-8)` | 8px | 表格单元格水平内边距 |
| `--density-cell-padding-y` | `var(--space-4)` | 4px | 表格单元格垂直内边距 |
| `--density-chart-padding` | `var(--space-8)` | 8px | 图表容器内边距 |
| `--density-font-delta` | 0 | — | 字号偏移量（0 = 不缩小） |

### 4.2 compact（默认）

全站默认档位，平衡信息密度与可读性。

| Variable | Value | Px | 说明 |
|----------|-------|----|------|
| `--density-row-height` | 2.25rem | 36px | 数据表格行高 |
| `--density-strip-height` | 2.25rem | 36px | Summary strip 高度 |
| `--density-header-height` | 2rem | 32px | 表头 / 面板头部高度 |
| `--density-input-height` | 2rem | 32px | 输入框高度 |
| `--density-action-height` | 2rem | 32px | 按钮高度 |
| `--density-chart-header` | 2rem | 32px | 图表头部高度 |
| `--density-panel-padding` | `var(--space-12)` | 12px | 面板内边距 |
| `--density-section-gap` | `var(--space-12)` | 12px | 区块间距 |
| `--density-cell-padding-x` | `var(--space-12)` | 12px | 表格单元格水平内边距 |
| `--density-cell-padding-y` | `var(--space-6)` | 6px | 表格单元格垂直内边距 |
| `--density-chart-padding` | `var(--space-12)` | 12px | 图表容器内边距 |
| `--density-font-delta` | 0 | — | 字号偏移量（0 = 不缩小） |

### 4.3 comfortable（宽松）

适用于演示模式、非专业用户界面、大屏展示。

| Variable | Value | Px | 说明 |
|----------|-------|----|------|
| `--density-row-height` | 2.625rem | 42px | 数据表格行高 |
| `--density-strip-height` | 2.5rem | 40px | Summary strip 高度 |
| `--density-header-height` | 2.25rem | 36px | 表头 / 面板头部高度 |
| `--density-input-height` | 2.25rem | 36px | 输入框高度 |
| `--density-action-height` | 2.25rem | 36px | 按钮高度 |
| `--density-chart-header` | 2.25rem | 36px | 图表头部高度 |
| `--density-panel-padding` | `var(--space-16)` | 16px | 面板内边距 |
| `--density-section-gap` | `var(--space-16)` | 16px | 区块间距 |
| `--density-cell-padding-x` | `var(--space-16)` | 16px | 表格单元格水平内边距 |
| `--density-cell-padding-y` | `var(--space-8)` | 8px | 表格单元格垂直内边距 |
| `--density-chart-padding` | `var(--space-16)` | 16px | 图表容器内边距 |
| `--density-font-delta` | 0 | — | 字号偏移量（0 = 不缩小） |

### 4.4 不受 Density 预设影响的变量

以下两个变量在所有密度档位中保持一致，不随预设切换变化：

| Variable | Value | Px | 说明 |
|----------|-------|----|------|
| `--density-gutter` | `var(--space-16)` | 16px | Shell gutter（壳层间距） |
| `--density-toolbar-height` | 2.25rem | 36px | 工具栏高度 |

### 4.5 切换机制

通过 `<html>` 元素的 `data-density` 属性进行全局切换：

```html
<!-- 高密模式 -->
<html data-density="dense" data-theme="dark">

<!-- 默认 compact 模式（可省略，compact 为默认值） -->
<html data-density="compact" data-theme="dark">

<!-- 宽松模式 -->
<html data-density="comfortable" data-theme="dark">
```

三档预设定义在 `tokens-density.css` 中，使用属性选择器覆盖 `:root` 中的默认值。

---

## 5. Market Color Region Switching

Market 域的颜色语义遵循**数值语义**（正数=上涨色，负数=下跌色），而非金融语义（涨跌情绪）。颜色映射通过 `[data-market-region]` 属性在 `<html>` 上切换。

### 5.1 CN 默认 — 红涨绿跌

默认值（无 `data-market-region` 属性或 `data-market-region="cn"`）：

| Token | 值 | 视觉 |
|-------|----|------|
| `--market-up-fg` | `oklch(0.670 0.170 20)` | 红色 |
| `--market-up-bg` | `oklch(0.670 0.170 20 / 0.10)` | 红色 10% 透明 |
| `--market-up-subtle` | `oklch(0.670 0.170 20 / 0.08)` | 红色 8% 透明 |
| `--market-down-fg` | `oklch(0.680 0.120 175)` | 绿色 |
| `--market-down-bg` | `oklch(0.680 0.120 175 / 0.10)` | 绿色 10% 透明 |
| `--market-down-subtle` | `oklch(0.680 0.120 175 / 0.08)` | 绿色 8% 透明 |

### 5.2 International — 绿涨红跌

通过 `[data-market-region="intl"]` 切换：

| Token | 值 | 视觉 |
|-------|----|------|
| `--market-up-fg` | `oklch(0.680 0.120 175)` | 绿色 |
| `--market-down-fg` | `oklch(0.670 0.170 20)` | 红色 |

**注意**：intl 模式下 `--market-up-bg`、`--market-up-subtle`、`--market-down-bg`、`--market-down-subtle` 已在 R2 中同步交换实现。

### 5.3 使用示例

```css
/* 正确：使用 domain semantic token */
.price-up {
  color: var(--market-up-fg);
  background: var(--market-up-bg);
}

.price-down {
  color: var(--market-down-fg);
  background: var(--market-down-subtle);
}

/* 错误：直接写死颜色 */
.price-up {
  color: oklch(0.670 0.170 20); /* ❌ 禁止 */
}
```

### 5.4 数值语义说明

Market 域 token 的命名基于数值方向（up/down），而非金融情绪（涨/跌）。这意味着：

- `--market-up-*` = 数值为正 = 价格上升 = 盈利方向
- `--market-down-*` = 数值为负 = 价格下降 = 亏损方向

CN 和 Intl 模式仅交换红绿色的映射关系，语义方向不变。

---

## 6. Theme Switching (Dark/Light)

### 6.1 约定

通过 `<html>` 元素的 `data-theme` 属性控制：

```html
<!-- 暗色模式（当前唯一实现） -->
<html data-theme="dark">

<!-- 亮色模式（计划中） -->
<html data-theme="light">
```

### 6.2 当前状态

- **Dark mode**：全站默认主题。所有页面均设置 `data-theme="dark"`。
- **Light mode**：R2 已实现。使用 Radix step-scale pattern（高 elevation → 低 lightness）。

### 6.3 Token 文件中的实现方式

在 `:root` 中定义 dark mode 作为默认值，light mode 值通过 `[data-theme="light"]` 属性选择器覆盖：

```css
:root {
  /* Dark mode values (default) */
  --surface-app: oklch(0.155 0.005 260);
  --text-primary: oklch(0.935 0.005 260);
  /* ... */
}

[data-theme="light"] {
  /* Light mode values — Radix step-scale pattern */
  --surface-app: oklch(0.985 0.002 260);
  --text-primary: oklch(0.155 0.015 260);
  /* ... */
}
```

### 6.4 已实现 Light mode 的文件

| 文件 | 覆盖范围 |
|------|---------|
| `tokens-semantic.css` | surface (6) + text (7) + border (3) + brand-subtle + scrollbar (3) + code (3) = 23 token |
| `tokens-interaction.css` | hover/active/dragging shadow 调整 = 3 token |
| `tokens-style.css` | surface + text + border + brand + interaction + code + scrollbar + prototype structural dimensions (`--panel-header-height`, `--tab-bar-height`, `--progress-bar-height`, `--surface-noise-opacity`) |

### 6.5 待实现 Light mode 的文件

| 文件 | 说明 |
|------|------|
| `tokens-data-viz.css` | 图表/热力图/资产色亮色适配 |
| `tokens-domain.css` | 域状态色 bg 值可能需要调整 |

### 6.6 实现优先级

Light mode 核心层（semantic + interaction + style override）已实现。
剩余 data-viz/domain 的亮色适配列为 P2 任务。

---

## 7. Color Space — OKLCH

### 7.1 格式规范

所有颜色值统一使用 **OKLCH** 格式。这是 R1 的硬性约束。

```
oklch(L C H)
oklch(L C H / A)
```

| 参数 | 范围 | 说明 |
|------|------|------|
| L (Lightness) | 0 - 1 | 感知亮度 |
| C (Chroma) | 0 - 0.4 | 色彩饱和度 |
| H (Hue) | 0 - 360 | 色相角度 |
| A (Alpha) | 0 - 1 | 不透明度（可选） |

### 7.2 选型理由

| 特性 | 说明 |
|------|------|
| 感知均匀 | 相同 L 值在不同色相下视觉亮度一致，避免 HSL 中"同亮度不同明暗"的问题 |
| Tailwind CSS v4 兼容 | Tailwind v4 原生支持 OKLCH，Ditto 的 token 可直接与 Tailwind 色彩体系对齐 |
| Alpha 支持 | `oklch(L C H / A)` 语法支持透明度，简化了需要多层透明度的 surface token |
| 广色域就绪 | OKLCH 可描述 P3 等广色域色彩，为未来高色阶显示设备做准备 |

### 7.3 使用约定

```css
/* 正确：使用 token */
.panel {
  background: var(--surface-panel-base);
  color: var(--text-primary);
  border: 1px solid var(--border-subtle);
}

/* 正确：需要临时色值时使用 OKLCH 格式 */
.temp-highlight {
  background: oklch(0.7 0.1 260 / 0.5);
}

/* 错误：使用其他色值格式 */
.bad {
  background: #1a1a2e;          /* ❌ HEX */
  color: rgb(255, 255, 255);    /* ❌ RGB */
  border: rgba(255, 0, 0, 0.3); /* ❌ RGBA */
}
```

---

## 8. R1 Quality Audit

### 8.1 清理目标

R1 审计范围：所有 CSS 文件中的 token 引用、hardcoded 色值、inline styles。

### 8.2 Before R1 — 发现的问题

| 问题类型 | 数量 | 位置分布 | 严重程度 |
|---------|------|----------|---------|
| operational `font-size-11` 引用 | 多处 | layout/prototype 页面 | 高 |
| `font-size-9` 引用（未定义 token） | 4 | 页面文件 | 高 |
| `--font-family-mono` 引用（未定义 token） | 2 | 页面文件 | 中 |
| `data-density="ultra"`（错误名称，应为 `dense`） | 1 | 页面文件 | 中 |
| Hardcoded oklch 色值 | 1 | layout-base.css | 低 |
| Hardcoded rgba 色值 | 2 | layout-base.css | 低 |
| `.data-table` 双重定义 | 1 | layout-base.css | 中 |

### 8.3 After R1 — 清理结果

| 问题类型 | Before | After | 状态 |
|---------|--------|-------|------|
| operational `font-size-11` | 多处 | 0 | ✅ 已限制在 dense 非交互元数据场景 |
| `font-size-9` | 4 | 0 | ✅ 已清理 |
| `--font-family-mono` (undefined) | 2 | 0 | ✅ 已补充定义 |
| `data-density="ultra"` | 1 | 0 | ✅ 已修正为 `dense` |
| Shell 层散落在 layout-base | ~7+ | 0 | ✅ R2 提取为 `tokens-shell.css` |
| Data Viz 层缺失 | — | 0 | ✅ R2 创建 `tokens-data-viz.css` |
| 色觉辅助符号缺失 | — | 0 | ✅ R2 添加 5 个 `--indicator-*` token |
| Hardcoded oklch (layout-base) | 1 | 0 | ✅ 已迁移至 token |
| Hardcoded rgba (layout-base) | 2 | 0 | ✅ 已迁移至 oklch token |
| `.data-table` 双重定义 | 1 | 0 | ✅ 已合并 |

### 8.4 Remaining Debt — 未清理项

| 问题类型 | 数量 | 分布 | 优先级 |
|---------|------|------|--------|
| Hardcoded oklch 色值（页面层，合法的 data-viz/动画/SVG） | ~80 | 3 个主页面文件 | — 不需清理 |
| Hardcoded oklch 色值（页面层，可替换） | ~20 | page-cross-market (tint/shadow), page-markets (sector/flow) | P2 |
| Inline styles | 207 | 13 个文件 | P2 |
| Layer 5/9 CSS 文件缺失 | — | — | P2 |
| Light mode data-viz/domain 适配 | — | — | P2 |
| Style Dictionary 管线缺失 | — | — | P3 |

---

## 9. Best Practice Evaluation Score

### 9.1 总分：78/100 (R2→R2.5 提升)

**评级：Tier 2 上沿 — Solid and Scalable（稳固可扩展）**

> R1 评分为 53/100。R2 提升至 68/100。R2.5 通过实现 Light mode、
> 清理 hardcoded oklch、迁移 overlay/frosted 至语义层、提取 Component 层，
> 提升至 78/100。

### 9.2 分项评分

| 维度 | 满分 | R1 | R2 | R2.5 | 变化 | 说明 |
|------|------|-----|-----|------|------|------|
| **Architecture** | 30 | 22 | 26 | 28 | +2 | 9/9 层全部落地，L5 Component 提取完成 |
| **Naming** | 25 | 20 | 22 | 23 | +1 | Overlay/frosted 迁移至语义层，层级归属更合理 |
| **Theming** | 20 | 12 | 14 | 18 | +4 | Light mode 核心层已实现（semantic + interaction + style） |
| **Governance** | 15 | 4 | 5 | 6 | +1 | 页面级局部 token 审计完成，清理冗余/no-op |
| **Anti-patterns** | 15 | -5 | -5 | +3 | +8 | Hardcoded oklch 从 136→~20（可替换），index.html 100% token 化 |

### 9.3 Tier 定义

| Tier | 分数范围 | 描述 |
|------|---------|------|
| Tier 1 | 80-100 | Production-grade（生产级） |
| **Tier 2** | **65-79** | **Solid and Scalable（稳固可扩展）** ← 当前 |
| Tier 3 | 50-64 | Functional but Fragile（可用但脆弱） |
| Tier 4 | 30-49 | Ad-hoc and Risky（临时且风险高） |

---

## 10. Optimization Roadmap

### P0 — Must Have（当前 Sprint）

| 任务 | 预期收益 | 复杂度 | 状态 |
|------|---------|--------|------|
| ~~Shell token 提取至独立 CSS 文件~~ | +2 pts | 中 | ✅ R2 完成 |
| ~~Data Viz 层创建~~ | +2 pts | 中 | ✅ R2 完成 |
| ~~色觉辅助符号 token~~ | +1 pt | 低 | ✅ R2 完成 |
| ~~Light mode surface/text/border 值实现~~ | +4 pts (Theming 14→18) | 中 | ✅ R2.5 完成 |
| ~~Hardcoded oklch 清理（主页面）~~ | +5 pts (Anti-patterns) | 中 | ✅ R2.5 大幅清理 |
| ~~Overlay/frosted 迁移至语义层~~ | +1 pt (Naming) | 低 | ✅ R2.5 完成 |
| ~~index.html 100% token 化~~ | — | 低 | ✅ R2.5 完成 |

### P1 — Should Have（下一 Sprint）

| 任务 | 预期收益 | 复杂度 | 状态 |
|------|---------|--------|------|
| ~~Density 切换激活至所有页面~~ | +2 pts (Architecture) | 低 | ✅ R2 完成 |
| ~~Market intl 模式 bg/subtle 补全~~ | +1 pt (Theming) | 低 | ✅ 已完成 |
| ~~Component token 层提取~~ | +2 pts (Architecture) | 中 | ✅ R2.5 完成 |
| ~~页面级局部 token 审计~~ | +1 pt (Governance) | 中 | ✅ R2.5 完成 |

### P2 — Nice to Have（后续迭代）

| 任务 | 预期收益 | 复杂度 |
|------|---------|--------|
| Inline styles 清理（207 处） | +3 pts (Anti-patterns) | 高 |
| Domain layer bg 值使用 `oklch(from...)` | +1 pt (Naming) | 低 |
| Module Pattern 层定义 | +1 pt (Architecture) | 中 |
| Light mode 图表/热力图适配 | +2 pts (Theming) | 中 |

### P3 — Future

| 任务 | 预期收益 | 复杂度 |
|------|---------|--------|
| Style Dictionary 管线搭建 | +5 pts (Governance) | 高 |
| 自动化 token 校验 CI | +2 pts (Governance) | 中 |

### 目标

完成 P0 + P1 后，当前评分 **78/100**（P0+P1 全部完成）。

完成 P2 后，预计总评分提升至 **85/100**，进入 **Tier 1 — Production-grade**。

---

## 附录 A：CSS 文件索引

| 文件 | 层 | 状态 |
|------|---|------|
| `tokens-base.css` | L1 Foundation | ✅ |
| `tokens-semantic.css` | L2 Semantic Surface | ✅ |
| `tokens-atmosphere.css` | L2b Atmosphere (Living Graphite) | ✅ |
| `tokens-shell.css` | L3 Shell | ✅ R2 新增 |
| `tokens-data-viz.css` | L4 Data Visualization | ✅ R2 新增 |
| `tokens-interaction.css` | L6 Interaction | ✅ |
| `tokens-domain.css` | L7 Domain Semantic | ✅ |
| `tokens-density.css` | L8 Density | ✅ |
| `tokens-style.css` | Override (Graphite Studio + prototype structural dimensions: `--panel-header-height`, `--tab-bar-height`, `--progress-bar-height`, `--surface-noise-opacity`) | ✅ |
| `layout-base.css` | Shared Layout | ✅ |
| `tokens-component.css` | L5 Component | ✅ R2.5 新增 |
| `tokens-module.css` | L9 Module Pattern | ❌ 待定义 |

## 附录 B：Attribute Switcher 索引

| 属性 | 挂载元素 | 可选值 | 默认值 | 控制范围 |
|------|---------|--------|--------|---------|
| `data-theme` | `<html>` | `dark`, `light` | `dark` | 全局主题 |
| `data-density` | `<html>` | `dense`, `compact`, `comfortable` | `compact` | 全局密度 |
| `data-market-region` | `<html>` | `cn`, `intl` | `cn` | Market 域颜色 |
| `data-domain` | `<html>` | `home`, `markets`, `research`, `trading`, `ai`, `platform` | `home` | Domain 签名色（Living Graphite） |

## 附录 C：命名速查

Token 命名统一遵循 `[layer].[family].[role].[state].[property]` 格式，属性名统一缩写：

| 属性 | 缩写 | 禁止使用 |
|------|------|---------|
| 背景 | `bg` | background |
| 前景/文本 | `fg` | text, color |
| 边框 | `border` | stroke |
| 阴影 | `shadow` | drop-shadow |
| 圆角 | `radius` | border-radius |
| 高度 | `height` | h |
| 宽度 | `width` | w |
| 内边距 | `padding` | p, pad |
| 间距 | `gap` | spacing, margin |
