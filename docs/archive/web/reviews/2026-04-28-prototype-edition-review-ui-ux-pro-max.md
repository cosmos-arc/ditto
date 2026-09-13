# Ditto 原型设计审核报告 — Edition Review (UI/UX Pro Max)

> **审核日期**：2026-04-28
> **审核范围**：29 页 HTML Prototype + 6 共享 CSS/JS，总计 83,581 行
> **审核标准**：UI/UX Pro Max 10 大类 99 条 UX 准则 + 项目视觉验证规范 + WCAG 2.1 AA
> **审核工具**：UI/UX Pro Max Design Intelligence、自动化 grep/aria 审计、逐页人工审核
> **分支**：feat/prototype-three-zone-architecture
> **提交**：3590c79

---

## 执行摘要

| 维度 | 评分 | 趋势 |
|------|:---:|:---:|
| **Shell 布局架构** | A | 多种 Shell 变体（v2/analytical/studio/agent）覆盖不同场景，Grid 声明精确 |
| **设计系统一致性** | A- | Token 覆盖率 90%+，但 13 个未定义变量、z-index/line-height 未 token 化 |
| **信息密度** | A | 数据密集型仪表盘的标杆水平，7-8 个 strip 指标行 + 双栏 + sidebar |
| **交互完整性** | B+ | Focus-visible 体系完善，但 46 个 `role="button"` 缺 aria-label |
| **三区架构** | B- | 核心页面 100% 覆盖，但 18/22 剩余页面缺失 Zone 标记 |
| **Accessibility** | B- | 基础达标（lang/title/aria-role），但 heading 跳级、skip-link 缺失、无 reduced-motion |
| **代码质量** | B | 零 inline style（HTML 层面），但 layout-base.css 有结构性 bug + 60+ magic number |
| **页面间一致性** | B- | Token 加载顺序 8 页有偏差，`oklch(from...)` vs `color-mix()` 不统一 |

**综合评价：B+**

设计系统架构扎实（OKLCH 色彩科学、10 层 Token 分层、Graphite Studio 材质层均为业界领先水平），但在 Token 完整性、Accessibility 和跨页一致性上存在系统性缺口。

---

## P0 — Critical（必须修复，阻塞交付）

### 1. layout-base.css `.filter-select` 结构性 Bug

**位置**：`shared/layout-base.css:1825-1828`

`.filter-select::after` 的闭合括号后出现 4 行游离属性（`appearance: none; cursor: pointer; transition`），与主体中的同名属性重复。浏览器容错但不属于"卓越代码质量"。

### 2. Token SSOT 断裂：13 个未定义变量

layout-base.css 引用了以下在 `src/styles/design-tokens/` 中**不存在**的变量：

| Token | 用途 | 引用位置 |
|-------|------|---------|
| `--brand-signature-glow` | Rail 激活态辉光 | layout-base.css:183 |
| `--risk-warning-fg` | 风控警告色 | layout-base.css:3452 |
| `--surface-secondary` | 表面色映射 | layout-base.css:3383 |
| `--radius-full` | 圆形头像/标签 | layout-base.css:3383-3384 |
| `--space-1` | 1px 级间距 | layout-base.css:3402 |
| `--shell-rail-radar-width` | Radar Shell rail 宽度 | layout-base.css:3282 |
| `--shell-activity-width` | Analytical Shell activity 宽度 | layout-base.css:2934 |
| `--shell-analysis-band-height` | 分析面板高度 | layout-base.css:2935 |

> **后果**：Prototype 渲染依赖浏览器 fallback（initial 值），React 端可能表现不同。Token SSOT 架构存在断裂。

### 3. 18/22 页面缺失三区架构

核心 5 页（Home / Trading / Risk / Studio / Agent）已完整实现 Zone 1-3，但其余 22 页中 **18 页完全没有 `proto-nav` 和 Zone 标记**。

缺失页面：page-a-shares, page-backtest-list, page-backtest-result, page-cross-market, page-experiment-list, page-factor-analysis, page-factor-list, page-instrument-hub, page-markets-calendar, page-markets-intelligence, page-markets-screener, page-orders-ledger, page-platform-settings, page-platform, page-portfolio, page-regime-monitor, page-research, page-strategies-detail, page-strategy-list, page-universe-list, page-watchlist, page-signals-inbox

> **后果**：状态变体（empty/loading/error）无系统化展示；弹层设计（Modal/Drawer/Toast）无集中展示；开发无法在 Prototype 中验证边界状态。

---

## P1 — High（应该修复，影响质量基线）

### 4. Token CSS 加载顺序不一致（8 页）

正确顺序：`base → semantic → atmosphere → domain → data-viz → interaction → density → component → shell → style`

| 问题类型 | 文件 | 详情 |
|----------|------|------|
| 缺少 `tokens-shell.css` | page-agent-console, page-cross-market, page-instrument-hub, page-strategies-detail | Shell 布局尺寸可能回退 |
| Token 顺序错误 | page-ai-overview, page-home, page-risk-center | CSS 级联可能导致值覆盖 |
| Shared CSS 顺序错误 | page-cross-market | prototype-toggles 优先级异常 |

### 5. z-index 无系统性管理

9 处硬编码 z-index 值，缺乏 token 管理。同一语义层级在不同 Shell 变体中数值不一致：

| Shell 变体 | Rail | Strip | Header |
|------------|------|-------|--------|
| `.shell` / `.shell-v2` | 10 | — | 120 |
| `.shell-radar` | 30 | 15 | 120 |
| `.shell-intel` | 30 | 14 | 120 |

> **建议**：提取为 `--z-rail: 10`, `--z-strip: 15`, `--z-header: 120`, `--z-overlay: 200`, `--z-modal: 1000`

### 6. line-height / letter-spacing 未 token 化

- **line-height**：4 种值（1.4/1.5/1.6/1.7）硬编码 10+ 处，无 token
- **letter-spacing**：3 种值（0/0.02em/0.04em）重复 35 次，无 token

> **建议**：提取为 `--lh-tight: 1.4`, `--lh-normal: 1.5`, `--lh-relaxed: 1.6`, `--lh-loose: 1.7`

### 7. 组件样式重复（DRY 违反）

| 重复对 | 行数 | 差异 |
|--------|------|------|
| `.header-action-btn` vs `.header-utility-btn` | 289-326 | 完全相同，应合并 |
| `.pulse-item` vs `.status-bar-item` | 411-482 | 结构相同，仅前缀不同 |
| `.flow-w-*` vs `.w-*` 宽度类 | 3341-3581 | 6 对完全重复 |
| `.style-label` / `.skip-link` / frosted header | 跨所有页面 | 每页重复定义，参数不一致 |

### 8. Accessibility 基础缺失

| 问题 | 影响文件 | 严重性 |
|------|---------|--------|
| 缺少 `<title>` + viewport meta | page-orders-ledger | High |
| 缺少 skip link | page-ai-overview, page-research | High |
| Heading 跳级（h1→h4、h2→h4） | page-a-shares, page-cross-market, page-markets-intelligence | Medium |
| ~46 个 `role="button"` 无 `aria-label` | 多个页面 | Medium |
| **零** `prefers-reduced-motion` 适配 | 全局 | Medium |
| Rail 用 `<div>` 而非 `<button>` | page-agent-console | Medium |
| 完全没有 heading 标签 | page-ai-overview, page-platform-settings | Medium |

### 9. `oklch(from...)` vs `color-mix()` 不统一

Agent Console 使用 19 处 `oklch(from var(--brand-accent) l c h / N)` 相对色语法，其余页面统一用 `color-mix(in oklch, ...)`。前者浏览器兼容性更差（Chrome 119+ vs Chrome 111+），应统一为 `color-mix`。

---

## P2 — Medium（建议改善，提升体验品质）

### 10. Home 页状态覆盖率仅 60%

作为用户入口页面，覆盖率（21/35 states）远低于其他页面（93-100%）。`stale` 和 `selected` 状态全部未实现。

### 11. 60+ 硬编码像素值（layout-base.css）

主要集中在：
- Icon 尺寸（16x16, 14x14, 6x6, 60x20）— 应提取为 token
- Grid 列宽（8px auto 60px 1fr...）— 表格级布局可保持
- 装饰性尺寸（3px, 20px, 48px x 4px）— 部分可 token 化

### 12. 响应式覆盖不足

3581 行 layout-base.css 仅 1 个 media query（Header 紧凑模式 @720px）。Shell Grid 窄屏折叠、数据表格水平滚动、三列布局响应均未处理。

> 作为 Prototype（固定 1536x900 viewport）可接受，React 实现需另行规划。

### 13. data-contract-slot 覆盖不均

| 页面 | Slot 数量 | 评价 |
|------|:---------:|------|
| Home | 11 | 良好 |
| Trading Overview | 8 | 良好 |
| Risk Center | 7 | 良好 |
| Strategy Studio | 2 | 不足 |
| Agent Console | 2 | 不足 |

Strategy Studio 和 Agent Console 的合同约束力弱，React 对齐时容易遗漏模块。

### 14. 页面级 CSS 体量偏大

| 页面 | `<style>` 行数 | 评价 |
|------|:--------------:|------|
| Agent Console | ~1700 | 过大 |
| Strategy Studio | ~1000 | 偏大 |

共享模式（`shell-studio`、`plan-card`、`agent-chain`）应提取到 `shared/` 目录。

### 15. 签名线渐变参数不一致

6 种不同参数的 `brand-signature-line` 渐变出现在不同页面中，缺乏统一规范。

---

## P3 — Low（锦上添花）

- 亚像素间距（1px/2px gap）无法 token 化，可标注为不可 token 化的亚像素微调
- `page-ai-overview.html` 和 `page-platform-settings.html` 完全没有 heading 标签
- Light mode 测试覆盖不足（所有页面默认 `data-theme="dark"`）
- `.col-small` vs `.col-80` 命名风格不统一
- 20/29 页面只使用 h4 级别标题，缺乏语义化标题层级

---

## 亮点与标杆

### 最佳页面：page-trading-overview.html

- **零 inline style** — 29 页中唯一完全达标
- 113 个 aria 属性 / 97 个 role 属性 — 交互可达性最高
- Session Strip + 两融数据行 + Pipeline Strip 三行创新布局
- SVG 权益曲线精细到 grid lines / axis labels / crosshair / glow filter

### 逐页综合评分

| 页面 | Shell 布局 | 信息密度 | 交互完整性 | 三区覆盖 | Token 合规 | 综合 |
|------|:---:|:---:|:---:|:---:|:---:|:---:|
| Home | A | A | B+ | B- (60%) | B | B+ |
| Trading Overview | A+ | A+ | A+ | A (93%) | A+ | **A+** |
| Risk Center | A | A | A | A+ (100%) | A | A |
| Strategy Studio | A+ | A+ | A | A+ (100%) | B | A |
| Agent Console | A | A | A- | A+ (100%) | B+ | A- |

### 设计系统优势

| 优势 | 评价 |
|------|------|
| 4 字体栈（Inter/Geist Sans/JetBrains Mono/Geist Mono） | 专业，角色分工清晰 |
| OKLCH + 域签名色体系 | 业界领先，色彩科学正确 |
| 10 层 Token 架构（base→semantic→atmosphere→domain→data-viz→interaction→density→component→shell→style） | 层次分明，SSOT 架构扎实 |
| Graphite Studio 材质层 | frosted glass + noise texture + ambient light 品质感高 |
| 涨跌色 + 风险等级色 + 数据可视化 token | 金融域色彩系统完整 |
| `font-display: swap` 全字体声明 | 性能最佳实践 |
| 纯 CSS 三区切换（radio + :has()） | 零 JS 依赖，工程优雅 |

---

## 行动计划（按优先级）

| 优先级 | 行动 | 工作量 | 负责人 |
|--------|------|--------|--------|
| P0-1 | 修复 `.filter-select` 结构 bug | 5 min | — |
| P0-2 | 在 `design-tokens/` 中补齐 13 个缺失 token | 30 min | — |
| P0-3 | 18 页补齐 Zone 标记（至少 Zone 1 default-view） | 2-4 hr | — |
| P1-4 | 统一 8 页 Token CSS 加载顺序 | 30 min | — |
| P1-5 | 提取 z-index / line-height / letter-spacing 为 token | 1 hr | — |
| P1-6 | 合并重复组件样式，提取页面共享模式到 shared/ | 2 hr | — |
| P1-7 | 修复 Accessibility 基础（title/skip-link/heading/aria-label） | 2 hr | — |
| P1-8 | 统一 `color-mix()` 替换 `oklch(from...)` | 30 min | — |
| P2-9 | Home 页补齐 stale/selected 状态至 ≥ 90% | 4 hr | — |
| P2-10 | Icon/fixture 尺寸 token 化 | 1 hr | — |

---

## 审核方法论

本次审核采用四层并行审计策略：

1. **自动化扫描**：grep 审计 inline style、accessibility 属性、token 引用、一致性检查
2. **核心 CSS 深度审核**：layout-base.css 3581 行逐项检查架构/间距/排版/响应式/动画/命名
3. **关键页面逐页审核**：Home / Trading / Risk / Studio / Agent 五页全维度审查
4. **剩余页面批量审核**：22 页结构性和一致性问题扫描
5. **UI/UX Pro Max 基准对比**：量化交易平台 + 数据密集仪表盘 + 暗色模式最佳实践

---

## 附录：UI/UX Pro Max 合规矩阵

基于 UI/UX Pro Max 10 大优先级类别的合规检查：

| Priority | Category | 状态 | 关键发现 |
|----------|----------|:---:|---------|
| 1 | Accessibility | ⚠️ | 对比度（OKLCH 体系保证）、Focus-visible 完善、Heading 跳级、Skip link 缺失 |
| 2 | Touch & Interaction | ✅ | 所有 hover/focus 态覆盖良好、cursor: pointer 一致 |
| 3 | Performance | ✅ | font-display: swap、零外部依赖、fontsource 本地化 |
| 4 | Style Selection | ✅ | Graphite Studio 风格统一、SVG 图标、无 emoji |
| 5 | Layout & Responsive | ⚠️ | 1536x900 固定 viewport、仅 1 个 media query |
| 6 | Typography & Color | ⚠️ | Token 覆盖 90%+、line-height/letter-spacing 未 token 化 |
| 7 | Animation | ⚠️ | Motion token 完整、无 prefers-reduced-motion |
| 8 | Forms & Feedback | ✅ | 状态变体（empty/loading/error）系统化 |
| 9 | Navigation | ✅ | Rail + Header + Sidebar 三层导航清晰 |
| 10 | Charts & Data | ✅ | 涨跌色编码、Sparkline SVG、数值格式化一致 |
