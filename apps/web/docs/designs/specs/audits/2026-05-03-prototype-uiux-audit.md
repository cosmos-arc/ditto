# Ditto Prototype Edition v1 — UI/UX 审计报告

> **审计范围**: 29 个活跃原型页面 + 2 个归档标本 + 设计规范 4 份
> **审计标准**: 最佳 UI 体验、美学、功能性和使用体验（不考虑改动成本）
> **审计日期**: 2026-05-03
> **审计方法**: 5 维度诊断扫描 + 跨页一致性分析 + 设计规范合规验证

---

## Audit Health Score

| # | Dimension | Score | Key Finding |
|---|-----------|-------|-------------|
| 1 | Accessibility | **3.0** | ARIA 覆盖良好但 focus-visible 和 CVD 编码存在跨页不一致 |
| 2 | Performance | **3.5** | 10 页存在 layout property transition，但整体克制 |
| 3 | Responsive Design | **2.5** | 仅桌面断点 (1536/1366/1200)，无移动端定义 |
| 4 | Theming | **3.8** | Token 体系极其完善，极少数硬编码颜色残留 |
| 5 | Anti-Patterns | **3.5** | 无 AI slop 特征，但 glow/gradient 有轻微过度使用 |
| **Total** | | **16.3/20** | **Good — 强大的设计系统基座，系统性问题集中在跨页一致性和无障碍细节** |

**Rating bands 参考**: 18-20 Excellent, 14-17 Good, 10-13 Acceptable, 6-9 Poor, 0-5 Critical

---

## Anti-Patterns Verdict

**通过。这个设计体系没有 AI slop 特征。**

逐一核查：

| AI Slop Tell | 状态 | 说明 |
|---|---|---|
| AI color palette (紫色渐变+霓虹蓝) | **无** | 使用 Graphite Studio 中性色 + Lapis hue 235° 签名色 |
| Gradient text | **无** | 所有文本纯色 |
| Glassmorphism | **轻度** | `backdrop-filter` 仅限 surface-frosted 层（panel header、header bar），功能性模糊 |
| Hero metrics 大数字仪表盘 | **无** | 数据展示以表格、面板、列表为主 |
| Card grids / Bento grid | **无** | 3-column market card grid 和 2-column candidate grid，信息驱动 |
| Generic fonts | **无** | 4-role 字体系统（Inter + Geist Sans + JetBrains Mono + Geist Mono） |
| Bounce easing | **无** | 全部使用 `cubic-bezier(0.4, 0, 0.2, 1)` 或 token 引用 |

**轻微关注点**：

- Glow 效果（`box-shadow` 呼吸动画）在 platform、home、screener、a-shares 较密集（11 处/页），但均为功能性状态指示
- Gradient 主要出现在进度条填充和数据可视化，少数用于 header 品牌签名渐变
- 按视觉宪章原则 5 的"克制"标准，glow 密度仍有优化空间

---

## Executive Summary

- **Audit Health Score**: 16.3/20 (Good)
- **Issues Total**: 42 (P0: 2, P1: 8, P2: 18, P3: 14)
- **Top 5 Critical Issues**:
  1. Focus-visible 实现跨页碎片化 — 4 种不同的 token 组合
  2. Alpha Explorer 缺少 candidate-card 和 queue-item 的键盘可达性
  3. Layout property transition（width/height）在 10 个页面触发重排
  4. Home 页 focus-visible 覆盖仅 1 处，与高 ARIA 覆盖不匹配
  5. Reduced-motion 覆盖差距：research 8 处 vs signals-inbox 1 处

---

## Detailed Findings by Severity

### P0 — Blocking（必须立即修复）

#### P0-1: Focus-visible 跨页碎片化

- **Location**: 全站 29 个原型
- **Category**: Accessibility
- **WCAG**: 2.4.7 Focus Visible (Level AA)
- **Impact**: 键盘用户在不同页面看到完全不同的焦点环样式，无法形成肌肉记忆

**4 种不同实现**：

| Token 组合 | 使用页面 |
|---|---|
| `outline: 1px solid var(--brand-accent)` | 大多数页面 |
| `box-shadow: 0 0 0 1.5px var(--brand-accent), 0 0 0 4px var(--interaction-selected-border)` | platform |
| `--interaction-focus-border` + `--interaction-selected-bg` | research |
| `--interaction-selected-border` | signals-inbox |

**Recommendation**: 全站统一为 `outline: 2px solid var(--interaction-focus-ring); outline-offset: 2px`，定义 `--interaction-focus-ring` 为 SSOT token。以 agent-console-v2 为基准。

---

#### P0-2: Alpha Explorer 键盘可达性缺失

- **Location**: `page-alpha-explorer.html`
- **Category**: Accessibility
- **WCAG**: 2.1.1 Keyboard (Level A)
- **Impact**: `.candidate-card` 和 `.queue-item` 有 `cursor: pointer` 但无 `tabindex="0"`，键盘用户完全无法访问核心交互元素

**Detail**:
- `tabindex` 统计：agent-console-v2(12) >> instrument-hub(36) >> strategy-studio(28) >> alpha-explorer(5)
- Alpha Explorer 的 candidate-card 和 queue-item 缺少 `tabindex="0"` + `focus-visible` 样式
- Alpha Explorer 的 focus-visible 仅 2 处（mode-tab 和 chip），远低于 strategy-studio(9) 和 instrument-hub(9)

**Recommendation**: 添加 `tabindex="0"` + `role="button"` + `focus-visible` 样式

---

### P1 — Major（发布前修复）

#### P1-1: Home 页 focus-visible 覆盖不足

- **Location**: `page-home.html` — 仅 1 处 focus-visible
- **Category**: Accessibility
- **Impact**: 首页有 17 个 role + 62 个 aria 属性（覆盖优秀），但交互元素缺少焦点指示器

**对比**:

| 页面 | role= | aria-= | tabindex= | focus-visible |
|---|---|---|---|---|
| home | 17 | 62 | 1 | **1** |
| instrument-hub | 43 | 114 | 36 | 9 |
| strategy-studio | 50 | 106 | 28 | 9 |
| agent-console-v2 | 20 | 57 | 12 | 6 |
| alpha-explorer | 26 | 69 | 5 | 2 |

**Recommendation**: 为所有 `.btn`、`.card`、`.tab`、`.filter-chip` 添加 `focus-visible` 样式

---

#### P1-2: Alpha Explorer CVD（色觉障碍）无障碍缺口

- **Location**: `page-alpha-explorer.html`
- **Category**: Accessibility
- **WCAG**: 1.4.1 Use of Color (Level A)
- **Impact**: 状态 pill 仅依赖颜色区分（running/warn/blocked），缺少 agent-console-v2 的 `::before` 图标编码

**Detail**: Agent-console-v2 使用以下非颜色编码：
- `.status-pill.running::before { content: "●" }` (filled dot)
- `.status-pill.warn::before { content: "▲" }` (triangle)
- `.status-pill.blocked::before { content: "✕" }` (cross)
- Score deltas: `data-delta="up"` → up-triangle, `data-delta="down"` → down-triangle

Alpha Explorer 缺少等价实现。

**Recommendation**: 为所有 status pill 添加 `::before` content 图标，与 agent-console-v2 对齐

---

#### P1-3: Layout property transition 触发重排

- **Location**: 10 个页面
- **Category**: Performance
- **Impact**: `transition: width/height` 触发浏览器 layout recalculation

**页面分布**:

| 页面 | layout transition 数 |
|---|---|
| research | 6 |
| regime-monitor | 5 |
| platform | 4 |
| risk-center | 2 |
| orders-ledger | 2 |
| markets-screener | 2 |
| agent-console | 2 |
| strategies-detail | 1 |
| signals-inbox | 1 |
| portfolio | 1 |

**Detail**: research 页有 6 处 `transition: width` 用于 IC bar 和 heatmap 渐变。具体示例：
- `transition: height var(--motion-duration-fast)` — collapsible panel
- `transition: width 0.6s` — IC bar fill animation
- `transition: width var(--motion-duration-normal)` — progress/gauge fill

**Recommendation**: 数据可视化一次性渐变可保留，但 collapsible panel 的 height transition 应改用 `grid-template-rows` 动画或 `transform: scaleY()`

---

#### P1-4: Reduced-motion 覆盖不均

- **Location**: 全站
- **Category**: Accessibility
- **WCAG**: 2.3.3 Animation from Interactions (Level AAA)
- **Impact**: 前庭功能障碍用户可能遭受不适

**覆盖对比**:

| 页面 | 动画效果数 | reduced-motion guards | 覆盖率 |
|---|---|---|---|
| research | ~5 | 8 | **超额** |
| screener | ~3 | 3 | 良好 |
| cross-market | ~4 | 2 | 不足 |
| signals-inbox | ~4 | **1** | **严重不足** |

signals-inbox 有 row-enter stagger、detail-slide-in、dot-pulse、scope-tab-enter 共 4 种动画，但仅 1 处 reduced-motion guard。

**Recommendation**: 统一标准 — 每个动画效果都应有对应的 `prefers-reduced-motion` 禁用规则

---

#### P1-5: 旧 agent-console 遗留硬编码颜色

- **Location**: `page-agent-console.html` — 37 处硬编码颜色
- **Category**: Theming
- **Impact**: 所有其他活跃原型已实现 0 硬编码颜色，旧版造成维护负担

**Recommendation**: 归档旧版 agent-console 或将其硬编码颜色迁移到 token 引用

---

#### P1-6: Strategy Studio 硬编码颜色残留

- **Location**: `page-strategy-studio.html` — 11 处
- **Category**: Theming
- **Impact**: Studio 模式高交互密度页面，dark mode 切换时可能产生不一致

**Recommendation**: 将所有 `rgba()` / `#hex` 替换为 `var(--*)` 或 `color-mix(in oklch, var(--*))`

---

#### P1-7: 硬编码 transition duration

- **Location**: 多页
- **Category**: Consistency
- **Impact**: 运动时间不一致，用户感知差异

**示例**:

| 页面 | 值 | 应使用 |
|---|---|---|
| alpha-explorer | `0.12s ease` | `var(--motion-duration-fast)` |
| agent-console-v2 | `100ms` | `var(--motion-duration-fast)` |
| research | `0.6s` | `var(--motion-duration-normal)` |

**Recommendation**: 全部引用 motion duration tokens

---

#### P1-8: Alpha Explorer 过于激进的 reduced-motion

- **Location**: `page-alpha-explorer.html`
- **Category**: Performance / Accessibility
- **Impact**: 通配符 `* { transition-duration: 0.01ms !important }` 覆盖所有 transition，包括功能性过渡

**Recommendation**: 改为针对性禁用动画，保留功能性过渡

---

### P2 — Minor（下一轮迭代修复）

#### P2-1: 面板 header 高度重复定义

- **Location**: agent-console-v2 + alpha-explorer — `38px` 出现在多个位置
- **Recommendation**: 提取为 `--panel-header-height: 38px` token

#### P2-2: Status bar 高度 fallback 碎片化

- **Location**: 多页 — `var(--status-bar-height, 24px)` 和直接 `24px` 混用
- **Recommendation**: 统一使用 token 引用，消除 fallback 硬编码

#### P2-3: Tab bar 高度未 token 化

- **Location**: agent-console-v2 — `42px` 硬编码
- **Recommendation**: 提取为 `--tab-bar-height` token

#### P2-4: Glow 效果密度偏高

- **Location**: platform、home、screener、a-shares（各 11 处 box-shadow glow）
- **Impact**: 视觉宪章原则 5 要求"克制"。虽为功能性 glow，11 处/页密度仍可能产生"发光体"印象
- **Recommendation**: 仅保留 critical 状态 glow，warn 降级为 static colored border

#### P2-5: Noise texture opacity 跨页不一致

- **Location**: cross-market `0.02` vs research `0.018`
- **Recommendation**: 统一为 `--surface-noise-opacity` token

#### P2-6: Backdrop-filter 多层叠加

- **Location**: cross-market(8)、agent-console(6)、其他页面(4)
- **Category**: Performance
- **Impact**: `backdrop-filter: blur()` GPU 密集，多层叠加影响低端设备
- **Recommendation**: 确保 frosted surface 层级不超过 2 层叠加；考虑低端设备降级为纯色背景

#### P2-7: 缺少 `<article>` 标签

- **Location**: 全站仅 12 处 `<article>` 标签
- **Category**: Accessibility
- **Impact**: card 组件（run-card、candidate-card、signal-row）语义上适合 `<article>`
- **Recommendation**: 独立内容卡片使用 `<article>` 替代 `<div>`

#### P2-8: `<footer>` 几乎未使用

- **Location**: 全站仅 1 处 `<footer>` 标签
- **Category**: Accessibility
- **Impact**: Status bar 语义上属于 `<footer>` landmark
- **Recommendation**: Status bar 使用 `<footer role="status">`

#### P2-9: Gradient 使用较密集

- **Location**: trading-overview(19)、risk-center(18)、platform(17)
- **Category**: Visual restraint
- **Impact**: 按宪章原则 5，gradient 应"克制使用"
- **Detail**: trading-overview 的 19 处 gradient 中，大部分是进度条/数据可视化填充（功能性），少量是 header 品牌签名渐变（可接受）
- **Recommendation**: 审查每处 gradient 是否有数据可视化功能，纯装饰性的应替换为纯色

#### P2-10–P2-14: 硬编码颜色残留

**残留页面**:

| 页面 | 硬编码颜色数 |
|---|---|
| agent-console (旧版) | 37 |
| strategy-studio | 11 |
| markets-calendar | 6 |
| markets-intelligence | 6 |
| instrument-hub | 6 |
| markets-screener | 5 |
| backtest-result | 4 |
| factor-analysis | 4 |
| orders-ledger | 4 |
| strategy-list | 2 |
| universe-list | 2 |
| watchlist | 2 |
| backtest-list | 1 |
| factor-list | 1 |

**Recommendation**: 逐页迁移到 token 引用。旧版 agent-console 应归档。

---

### P3 — Polish（时间允许时修复）

1. 部分 progress bar 高度 `6px` 未 token 化
2. Delta arrow `::before` 使用 `8px` 硬编码字号
3. Pareto chart 标签使用 `var(--font-size-9, 9px)` fallback 暗示 token 缺失
4. Copilot Rail 使用固定 `308px` 宽度
5. Research 页 `font-size-11` 已合并但注释仍在
6. Alpha Explorer `.chip` 无 hover transition
7. Agent Console v2 的 `100ms` transition 应使用 token
8. 多页 `1px` border width 未统一为 token
9. 部分 tooltip 模块使用 `data-tooltip` 但无 ARIA 关联
10. Strategy Studio 的 `::before` 图标使用 Unicode 而非 SVG sprite
11. Heatmap cell 缺少 `role="gridcell"`
12. Sparkline SVG 缺少 `aria-label` 描述
13. 几个页面的 `<h1>` 内嵌 style label（`aria-hidden="true"` 已处理）
14. 部分 overlay 缺少 `role="dialog"` 标记

---

## Patterns & Systemic Issues

### 1. Focus-visible 碎片化

**29 个页面使用至少 4 种不同 focus 环实现。**

根因：交互规范（04_interaction_state_spec.md）定义了 focus-visible baseline，但未指定具体的 token 映射。各页面独立实现导致碎片化。

### 2. Reduced-motion 覆盖不均

**research(8) >> screener(3) >> cross-market(2) >> signals(1)。**

页面动画数量与 reduced-motion guard 数量不成比例。根因：缺乏"每动画必 guard"的自动化检查机制。

### 3. Layout dimension tokenization 不完整

`38px` panel header、`24px` status bar、`42px` tab bar 等高频布局尺寸散布在多页 `<style>` 中。

根因：`tokens-shell.css` 定义了 shell-level dimensions，但 sub-shell 组件尺寸未覆盖。

### 4. 旧版页面遗留债务

`page-agent-console.html`（37 处硬编码颜色）与 v2 并存。需要决定归档或迁移策略。

---

## Positive Findings

1. **零 inline styles**: 所有 29 个活跃原型达到 0 inline style
2. **Token 体系极其成熟**: 9 层 token 文件 + `color-mix(in oklch)` 广泛使用，色彩管理业界顶尖
3. **Shell Family 架构清晰**: 7 种 shell 类型映射明确，跨页结构可辨识
4. **Primary Answer 契约**: 所有页面实现 `data-primary-answer` 语义标注
5. **Skip link 全覆盖**: 所有页面都有 skip-link
6. **State variant 100%**: 所有页面实现 default/loading/empty/error/stale 完整状态
7. **Shared JS library**: prototype-interactions.js（1846 行）提供 11 种可复用交互模块
8. **Semantic token references**: 新页面（agent-console-v2、alpha-explorer）达到 0 硬编码颜色
9. **`font-variant-numeric: tabular-nums`**: 全站数字显示统一使用等宽数字
10. **Design Spec 忠实度**: 宪章 8 条原则在原型中得到忠实体现

---

## Recommended Actions

| # | Priority | Command | Description |
|---|---|---|---|
| 1 | P0 | `/normalize` | 统一全站 focus-visible，定义 `--interaction-focus-ring` SSOT |
| 2 | P0 | `/harden` | Alpha Explorer 添加 tabindex + focus-visible + CVD 状态编码 |
| 3 | P1 | `/harden` | Home 页补全 focus-visible 覆盖 |
| 4 | P1 | `/normalize` | 统一 reduced-motion 覆盖标准 |
| 5 | P1 | `/optimize` | 审查 layout property transition |
| 6 | P1 | `/normalize` | Strategy Studio + 旧版 agent-console 硬编码颜色 token 化 |
| 7 | P1 | `/normalize` | 统一 transition duration token 引用 |
| 8 | P1 | `/harden` | Alpha Explorer reduced-motion 从通配符改为针对性 |
| 9 | P2 | `/normalize` | 提取 panel-header-height / tab-bar-height 为共享 token |
| 10 | P2 | `/polish` | 审查 glow 密度，非 critical 状态降级 |
| 11 | P2 | `/normalize` | Noise texture opacity 和 status bar height 统一 token 化 |
| 12 | P3 | `/polish` | 语义 HTML 标签优化（article、footer） |

---

## Best Practice Recommendations（不考虑改动成本）

### 1. 统一 Focus Ring 系统

定义全站 `--focus-ring` 复合 token：

```css
:focus-visible {
  outline: 2px solid var(--interaction-focus-ring);
  outline-offset: 2px;
  border-radius: var(--radius-2);
}
```

放入 `layout-base.css` 或新建 `shared/focus-ring.css`，所有原型通过 `@import` 引入。

### 2. 引入 Automated A11y Gate

在 prototype gates 中新增检查项：
- focus-visible count >= interactive element count × 0.5
- reduced-motion guard count >= animation count
- tabindex audit：所有 `cursor: pointer` 元素必须有 `tabindex="0"`

### 3. Gradient 和 Glow 节制策略

制定明确的 glow 使用规则：
- **允许**: critical 状态呼吸动画、品牌签名线微弱渐变
- **限制**: warn 状态降级为 static colored border
- **禁止**: 无业务语义的装饰性发光

### 4. Layout Dimension Token 完整化

在 `tokens-shell.css` 中补全：

```css
--panel-header-height: 38px;
--tab-bar-height: 42px;
--status-bar-height: 24px; /* 已存在但 fallback 碎片化 */
--progress-bar-height: 6px;
--surface-noise-opacity: 0.02;
```

---

## 数据附录

### 硬编码颜色统计（全站）

| 页面 | 数量 |
|---|---|
| agent-console (旧版) | 37 |
| strategy-studio | 11 |
| markets-calendar | 6 |
| markets-intelligence | 6 |
| instrument-hub | 6 |
| markets-screener | 5 |
| backtest-result | 4 |
| factor-analysis | 4 |
| orders-ledger | 4 |
| strategy-list | 2 |
| universe-list | 2 |
| watchlist | 2 |
| backtest-list | 1 |
| factor-list | 1 |
| 其余 15 页 | **0** |

### 语义 HTML 统计（全站合计）

| Tag | Count |
|---|---|
| `<section>` | 125 |
| `<nav>` | 59 |
| `<header>` | 29 |
| `<aside>` | 23 |
| `<article>` | 12 |
| `<main>` | 9 |
| `<footer>` | 1 |

### Focus-visible 分布

| 页面 | role= | aria-= | tabindex= | focus-visible |
|---|---|---|---|---|
| instrument-hub | 43 | 114 | 36 | 9 |
| strategy-studio | 50 | 106 | 28 | 9 |
| alpha-explorer | 26 | 69 | 5 | 2 |
| agent-console-v2 | 20 | 57 | 12 | 6 |
| home | 17 | 62 | 1 | 1 |

### Gradient / Glow 分布

| 页面 | gradient | backdrop-filter | box-shadow glow |
|---|---|---|---|
| trading-overview | 19 | 4 | — |
| risk-center | 18 | 4 | — |
| platform | 17 | 4 | 11 |
| regime-monitor | 14 | 4 | 6 |
| home | 11 | — | 11 |
| strategy-studio | 7 | 4 | — |
| instrument-hub | 7 | — | — |
| cross-market | — | 8 | 9 |

### Layout Transition 分布

| 页面 | layout property transition |
|---|---|
| research | 6 |
| regime-monitor | 5 |
| platform | 4 |
| risk-center | 2 |
| orders-ledger | 2 |
| markets-screener | 2 |
| agent-console | 2 |
| strategies-detail | 1 |
| signals-inbox | 1 |
| portfolio | 1 |
