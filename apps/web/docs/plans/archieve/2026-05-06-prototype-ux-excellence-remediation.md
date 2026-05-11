# Prototype UX Excellence Remediation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 Ditto 原型从"工程化成熟的 Graphite Studio"推进到"具备数据生命感的专家工作台"——对标 Bloomberg 的实时脉动、TradingView 的专业图表质感、Linear 的导航流畅度。

**Scope:** 仅原型层（HTML/CSS/JS），不涉及 React 实现。

**Source:** /impeccable:audit 严格审计报告（16/20 Good），筛选出**未被现有修复计划覆盖**的发现。

---

## 与现有计划的关系

本计划专注新增发现，以下审计项已在其他计划中处理，**不重复**：

| 审计发现 | 已覆盖计划 | 状态 |
|---|---|---|
| 图表交互合同 + 交互式原型 | `2026-05-04-prototype-best-uiux-optimization-plan.md` Phase 3 | 进行中 |
| 面板 Resize 持久化 | 同上 Phase 4 Task 4.2 | 进行中 |
| CVD 色觉缺陷 | 同上 Phase 5 + `2026-05-04-prototype-audit-remediation.md` Task 1.1 | 进行中 |
| Reduced Motion 覆盖 | 同上 Phase 5 Task 5.2 | 进行中 |
| Skeleton 标准化 | 同上 Phase 1 Task 1.2 | 进行中 |
| Command Palette Action Bus | 同上 Phase 2 Task 2.1 | 进行中 |
| Light Theme 修复 | `2026-05-04-prototype-audit-remediation.md` Task 1.2 | 进行中 |
| 信息密度渐进式披露 | 同上 Task 1.3 | 进行中 |
| 数据新鲜度视觉分层 | 同上 Task 1.4 | 进行中 |
| Glow Budget | `2026-05-04-prototype-best-uiux-optimization-plan.md` Task 1.4 | 进行中 |

---

## Definition Of Done

- 所有修改页面 `bun run prototype:gates` 通过
- 零新增 inline style
- 所有新增动画有 `prefers-reduced-motion` 保护
- 所有新增交互元素有 `focus-visible` ring
- 新增 CSS 变量在 `tokens-style.css` 或页面 `<style>` 中定义（禁止 inline）
- Edition Manifest score 不降低

---

## Phase 1: Data Liveness — 数据生命感 `[P0]`

> 核心理念：量化工具的第一个感知信号是"数据在流动"。Bloomberg 的价格跳动、TradingView 的平滑插值传递的信息是"这个系统是活的"。

### Task 1.1: 数字平滑过渡动画 `[M]`

**验收:**
- 所有 `--font-family-numeric` 的 `.metric-value` / `.object-price` 元素有 data-update 微动效
- 动效：`translateX(2px) → 0`（右滑入）+ `opacity 0.85 → 1`，200ms，`motion-easing-standard`
- `prefers-reduced-motion: reduce` 下跳过动画，直接更新
- 不影响 prefers-color-scheme

**文件:**
- Modify: `docs/designs/specs/prototypes/shared/layout-state.css` — 添加 `.data-updated` keyframe + class
- Modify: `docs/designs/specs/prototypes/shared/prototype-interactions.js` — DataCounter 模块增强，自动检测 `data-contract-slot` 内的 numeric 元素
- Modify: `docs/designs/specs/prototypes/page-home.html` — Decision Card metric-values 应用 `.data-updated`
- Modify: `docs/designs/specs/prototypes/page-instrument-hub.html` — object-price 应用 `.data-updated`
- Modify: `docs/designs/specs/prototypes/page-cross-market.html` — market-card-index 应用 `.data-updated`

**Steps:**
1. 在 `layout-state.css` 中定义 `@keyframes data-tick`：
   ```css
   @keyframes data-tick {
     0%   { opacity: 0.85; transform: translateX(2px); }
     100% { opacity: 1; transform: translateX(0); }
   }
   .data-updated {
     animation: data-tick var(--motion-duration-normal) var(--motion-easing-standard);
   }
   ```
2. 添加 `prefers-reduced-motion` 覆盖（已存在于 `layout-state.css`，确认 `.data-updated` 被覆盖）
3. 在 `prototype-interactions.js` 的 `DataCounter` 模块中，当数值变化时自动添加 `.data-updated` class，300ms 后移除
4. 在 3 个核心页面（Home、Instrument Hub、Cross-Market）的关键数值元素上验证效果

**测试:** 确认 `data-tick` keyframe 存在、`.data-updated` 有 prefers-reduced-motion 保护

---

### Task 1.2: Sparkline 脉冲点指示器 `[S]`

**验收:**
- 所有 `.sparkline` / `.card-sparkline` SVG 末端有一个 3px 脉冲圆点
- 脉冲颜色跟随 sparkline 的语义色（上涨=up-fg，下跌=down-fg，中性=text-tertiary）
- 脉冲动画：`scale(1) → scale(1.6) → scale(1)`，3s ease-in-out infinite
- `prefers-reduced-motion` 下脉冲停止，圆点保持静态

**文件:**
- Modify: `docs/designs/specs/prototypes/shared/layout-state.css` — 添加 `.sparkline-dot-pulse` keyframe
- Modify: `docs/designs/specs/prototypes/shared/layout-components.css` — `.sparkline` 伪元素或 SVG circle 样式
- Modify: 使用 sparkline 的页面 — 添加末端脉冲圆点

**Steps:**
1. 定义 keyframe：
   ```css
   @keyframes sparkline-pulse {
     0%, 100% { r: 2; opacity: 1; }
     50% { r: 4; opacity: 0.6; }
   }
   ```
2. 在 `prototype-interactions.js` 的 `Sparkline` 模块中，生成 sparkline SVG 后追加 `<circle>` 末端圆点
3. 圆点颜色取自 `data-sparkline-color` 属性或从 sparkline polyline stroke 继承
4. 在 Cross-Market 的 market cards、Instrument Hub 的 key metrics、Home 的 global pulse sparklines 上验证

**测试:** grep 确认 `sparkline-pulse` keyframe 存在且有 reduced-motion 覆盖

---

### Task 1.3: 全局数据连接状态 LED `[S]`

**验收:**
- Shell header 的 utility bar 中添加一个 6px LED 状态指示灯
- 状态颜色：connected=brand-accent（脉冲），degraded=amber-500（静态），disconnected=red-500（闪烁）
- 位于 theme/density toggle 旁边
- 带 `aria-label="数据连接状态: 正常"` 的可访问性标注

**文件:**
- Modify: `docs/designs/specs/prototypes/shared/layout-shell.css` — header utility bar 中 `.header-led` 位置
- Modify: `docs/designs/specs/prototypes/shared/layout-state.css` — LED 脉冲动画（复用 `dot-pulse`）
- Modify: 所有 `page-*.html` — header utility area 添加 LED 元素

**Steps:**
1. 在 `layout-shell.css` 的 `.header-utilities` 区域定义 `.header-led` 样式：
   ```css
   .header-led {
     width: var(--status-dot-size, 6px);
     height: var(--status-dot-size, 6px);
     border-radius: 50%;
     background: var(--system-healthy-fg);
     animation: dot-pulse 3s ease-in-out infinite;
   }
   ```
2. 在 header utility bar 的 theme toggle 之前插入 LED（因为这是最通用的位置）
3. 用 shared mock-data 控制 LED 状态

**测试:** 确认 LED 在 3+ 页面存在、有 aria-label、有 prefers-reduced-motion 保护

---

## Phase 2: Signature Components — 签名组件重塑 `[P1]`

> 核心理念：Home 的 Global Pulse 和 Decision Card 应该是用户记住 Ditto 的两个元素。

### Task 2.1: Global Pulse 签名化重设计 `[L]`

**验收:**
- Global Pulse 核心指标（前 3 项）字号放大至 `--font-size-24`，其余保持 `--font-size-12`
- 每项右侧嵌入 48×20 sparkline
- 上涨项背景 `--market-up-fg at 4%`，下跌 `--market-down-fg at 4%`，中性无色
- 保持现有 8 列 grid 布局不破坏
- 移动端（<1024px）降级为 4 列

**文件:**
- Modify: `docs/designs/specs/prototypes/page-home.html` — `.global-pulse` 重构
- Modify: `docs/designs/specs/prototypes/shared/mock-data.js` — 补充 sparkline 数据
- Read: `docs/designs/specs/prototypes/shared/layout-components.css` — 复用 `.card-sparkline` 模式

**Steps:**
1. 重构 `.global-pulse-item` CSS：
   - 前 3 项添加 `.global-pulse-item--hero` class，调整 layout 为 horizontal（label+value 左，sparkline 右）
   - `.global-pulse-value--hero { font-size: var(--font-size-24); }`
   - 背景色语义化：`[data-direction="up"] { background: color-mix(in oklch, var(--market-up-fg) 4%, transparent); }`
2. 在 `mock-data.js` 的 `todayPulse` 数组中添加 `sparkline` 和 `direction` 字段
3. 使用 `prototype-interactions.js` 的 `Sparkline` 模块渲染迷你 sparkline
4. 添加 `@media (max-width: 1023px)` 断点，grid 降级为 `repeat(4, 1fr)`

**测试:** 确认 hero 项字号为 24px、非 hero 项保持 12px、sparkline 存在、背景色正确

---

### Task 2.2: Decision Card 视觉冲击力增强 `[M]`

**验收:**
- 判断文字从 `--font-size-16` → `--font-size-20`（需确认 tokens 中有此档位或使用 `clamp()`）
- 左侧竖线从 2px → 3px，加呼吸动画（opacity 0.7↔1.0，3s ease-in-out）
- CTA primary 添加微弱品牌色光晕（`box-shadow: 0 0 12px brand-accent at 20%`）
- Risk level 文字替换为 BulletGraph 微型条

**文件:**
- Modify: `docs/designs/specs/prototypes/page-home.html` — `.decision-card` 样式调整
- Modify: `docs/designs/specs/prototypes/shared/layout-components.css` — `.decision-card-judgment` 字号
- Read: `docs/designs/specs/prototypes/shared/prototype-interactions.js` — BulletGraph 模块

**Steps:**
1. 在 tokens-style.css 中确认或添加 `--font-size-20: 1.25rem`（设计 token 变更，需遵循审批流程）
2. 调整 `.decision-card::before`（左侧竖线）：
   ```css
   width: 3px;
   background: color-mix(in oklch, var(--brand-signature-fg) 62%, transparent);
   animation: border-breathe 3s ease-in-out infinite;
   ```
3. 添加 `@keyframes border-breathe { 0%,100%{opacity:0.7} 50%{opacity:1} }`
4. CTA primary hover 增强光晕
5. Risk level 区域添加 `data-bullet-graph` 属性，用 BulletGraph 模块渲染

**测试:** 确认判断文字 20px、竖线 3px 有呼吸动画、CTA hover 有光晕

---

### Task 2.3: 告警流式流入动画 `[M]`

**验收:**
- 新告警从顶部滑入（`translateY(-100%) → 0`，200ms `motion-easing-emphasis`）
- Critical 告警顶部边框闪烁 2 次（每次 200ms，`--risk-critical-fg`）
- 告警项可标记已读（点击 `data-answer-action="dismiss-alert"` 后淡出）
- Header utility bar 显示未读告警 badge 计数

**文件:**
- Modify: `docs/designs/specs/prototypes/page-home.html` — alerts 区域动画
- Modify: `docs/designs/specs/prototypes/shared/layout-state.css` — `@keyframes alert-slide-in` + `alert-flash-border`
- Modify: `docs/designs/specs/prototypes/shared/prototype-interactions.js` — 新增 `AlertStream` 模块或扩展 `ScrollReveal`

**Steps:**
1. 定义告警动画 keyframes：
   ```css
   @keyframes alert-slide-in {
     from { transform: translateY(-100%); opacity: 0; }
     to { transform: translateY(0); opacity: 1; }
   }
   @keyframes alert-flash-border {
     0%, 100% { border-top-color: transparent; }
     50% { border-top-color: var(--risk-critical-fg); }
   }
   ```
2. 告警项添加 `.alert-item--new` class 触发 slide-in
3. Critical 告警添加 `.alert-item--critical` 触发 flash-border（2 次后停止）
4. Dismiss action 点击后 `.alert-item` 添加 `.alert-dismissing`（`opacity 0 → 0, max-height` 收缩），300ms 后 `display: none`
5. Header badge 计数用 `.badge-count` 组件（已存在于 layout-components.css）

**测试:** 确认动画 keyframes 存在、dismiss 后元素隐藏、badge 更新

---

## Phase 3: Navigation & Context — 导航流畅度 `[P1]`

### Task 3.1: Breadcrumb 导航系统 `[M]`

**验收:**
- Header 标题区域左侧添加 breadcrumb：`Home / Markets / Cross-Market`
- 层级用颜色区分：`--text-tertiary` / `--text-secondary` / `--text-primary`（当前页）
- 分隔符用 `/` + `space-4` 间距
- 每个层级可点击（`role="link"`），当前页不可点击
- 支持 `⌘[` / `⌘]` 键盘后退/前进

**文件:**
- Modify: `docs/designs/specs/prototypes/shared/layout-shell.css` — `.header-breadcrumb` 样式
- Modify: `docs/designs/specs/prototypes/shared/prototype-interactions.js` — KeyboardShortcuts 扩展
- Modify: 代表性页面（Home, Cross-Market, Instrument Hub, Trading Overview）— 添加 breadcrumb HTML

**Steps:**
1. 在 `layout-shell.css` 中定义 breadcrumb 组件：
   ```css
   .header-breadcrumb {
     display: flex;
     align-items: center;
     gap: var(--space-4);
     font-size: var(--font-size-12);
   }
   .breadcrumb-item { color: var(--text-tertiary); cursor: pointer; }
   .breadcrumb-item:hover { color: var(--text-secondary); }
   .breadcrumb-item--current { color: var(--text-primary); cursor: default; }
   .breadcrumb-sep { color: var(--text-quaternary); }
   ```
2. 在 header 的 `.header-title` 之前插入 breadcrumb（仅非 Home 页面）
3. Breadcrumb 数据从页面 `<meta name="breadcrumb">` 或 JS 配置读取
4. 扩展 KeyboardShortcuts：`Alt+ArrowLeft` = 后退，`Alt+ArrowRight` = 前进

**测试:** 确认 breadcrumb 在 4+ 页面存在、颜色层级正确、键盘快捷键响应

---

## Phase 4: Interaction Polish — 交互精修 `[P2]`

### Task 4.1: 表格行悬停增强 `[S]`

**验收:**
- 悬停行左侧出现 2px `--brand-accent` 竖线指示器
- 行内数值型数据（`.metric-value`, `[data-numeric]`）微弱高亮
- 悬停行上下 divider 升级为 `--border-default`

**文件:**
- Modify: `docs/designs/specs/prototypes/shared/layout-components.css` — data table 行样式

**Steps:**
1. 添加表格行悬停增强：
   ```css
   .data-table tbody tr:hover {
     background: var(--interaction-hover-subtle-bg);
     border-left: 2px solid var(--brand-accent);
     padding-left: calc(var(--space-12) - 2px);
   }
   .data-table tbody tr:hover td {
     border-top-color: var(--border-default);
     border-bottom-color: var(--border-default);
   }
   ```
2. 确认不影响已有的行选中态（`.row-selected`）

**测试:** 在 Watchlist / Signals Inbox / Orders Ledger 页面验证悬停效果

---

### Task 4.2: Frosted Glass 差异化使用 `[M]`

**验收:**
- 有滚动内容的页面（Home, Cross-Market, Research）→ 保留 frosted header
- 无滚动的固定布局（Instrument Hub, Factor Analysis）→ 改为纯色 + domain 签名色渐变
- Context bar / Scope strip 的 frosted 处理同理

**文件:**
- Modify: `docs/designs/specs/prototypes/page-instrument-hub.html` — header 覆盖
- Modify: `docs/designs/specs/prototypes/page-factor-analysis.html` — header 覆盖
- Modify: `docs/designs/specs/prototypes/page-strategies-detail.html` — header 覆盖
- Read: `docs/designs/specs/prototypes/shared/layout-shell.css` — 默认 frosted 行为

**Steps:**
1. Hub 类页面（instrument-hub, factor-analysis, strategies-detail, backtest-result）在页面 `<style>` 中覆盖：
   ```css
   .shell-hub .shell-header {
     backdrop-filter: none;
     -webkit-backdrop-filter: none;
     background: linear-gradient(
       to right,
       var(--surface-panel-base),
       color-mix(in oklch, var(--brand-signature-fg) 3%, var(--surface-panel-base))
     );
   }
   ```
2. 验证 Light Theme 下覆盖仍然可读
3. 不修改 shared CSS 的默认 frosted 行为（避免破坏其他页面）

**测试:** 确认 Hub 页面 header 无 backdrop-filter、带签名色渐变；其他页面不受影响

---

### Task 4.3: Sidebar Hover Peek 模式 `[M]`

**验收:**
- Sidebar 折叠态（56px）hover 时，内容覆盖展开为 `min-content`（overlay 模式）
- 展开 overlay 有 `--surface-overlay` 背景 + `box-shadow`
- 鼠标离开后延迟 300ms 自动收回
- 不影响主内容区域布局

**文件:**
- Modify: `docs/designs/specs/prototypes/shared/layout-shell.css` — sidebar hover overlay
- Modify: `docs/designs/specs/prototypes/shared/prototype-interactions.js` — 扩展 SidebarToggle 模块

**Steps:**
1. 定义 sidebar peek overlay 样式：
   ```css
   .shell-sidebar-collapsed:hover .sidebar-peek-overlay {
     display: block;
     position: absolute;
     left: var(--shell-rail-width);
     top: var(--shell-header-height);
     bottom: 0;
     width: var(--shell-sidebar-width);
     background: var(--surface-overlay);
     box-shadow: 4px 0 12px oklch(0 0 0 / 0.15);
     z-index: 50;
     animation: sidebar-peek-in var(--motion-duration-fast) var(--motion-easing-standard);
   }
   ```
2. 用 JS `mouseenter` / `mouseleave` 延迟控制（300ms debounce）
3. Peek overlay 内渲染完整 sidebar 内容的克隆

**测试:** 在 Home / Trading Overview 页面验证 sidebar hover 展开/收回

---

### Task 4.4: 空状态 CTA 引导 `[S]`

**验收:**
- 所有 `.state-empty` 有一个 primary CTA 按钮
- CTA 指向最可能的下一步操作（如 "创建策略"、"添加标的"）
- 空状态插图使用 domain 签名色（非通用灰色）

**文件:**
- Modify: `docs/designs/specs/prototypes/shared/layout-gallery.css` — `.state-empty .empty-cta`
- Modify: 代表性页面的 state-empty 模板 — 添加 CTA

**Steps:**
1. 在 `layout-gallery.css` 中定义 `.empty-cta` 样式：
   ```css
   .state-empty .empty-cta {
     margin-top: var(--space-12);
     padding: var(--space-4) var(--space-10);
     border: 1px solid var(--brand-accent);
     border-radius: var(--radius-4);
     color: var(--brand-accent);
     font-size: var(--font-size-12);
     font-weight: var(--font-weight-medium);
     cursor: pointer;
   }
   ```
2. 在 `.state-empty .empty-icon` 中将颜色从通用 gray 改为 `var(--brand-signature-fg)`
3. 在 3+ 页面的空状态模板中添加 CTA 按钮

**测试:** 确认空状态有 CTA、图标使用 domain 签名色

---

## Phase 5: Coverage & Polish — 覆盖率与收尾 `[P3]`

### Task 5.1: Home 页面 State Coverage 61% → 100% `[M]`

**验收:**
- 补齐 `stale` 状态：global-pulse, decision-card, pending-actions, alerts-market, recent-signals, data-health 各 1 个 stale variant
- 补齐 `selected` 状态：pending-actions, recent-signals 各 1 个 selected variant（有选中高亮）
- Manifest coverage 更新为 100%

**文件:**
- Modify: `docs/designs/specs/prototypes/page-home.html` — states gallery 补充
- Modify: `docs/designs/specs/prototypes/.edition-manifest.json` — coverage 更新

**Steps:**
1. 为每个组件添加 stale 状态卡片：
   - 使用 `--text-data-stale` 颜色（oklch(0.660 0.020 55) 暖色调）
   - 添加 stale indicator（静态灰点 + "数据过期" 标签）
   - 添加刷新 CTA
2. 为 pending-actions 和 recent-signals 添加 selected 状态：
   - 选中行 `background: var(--interaction-selected-bg)`
   - 左侧 `2px solid var(--brand-accent)` 指示
3. 更新 manifest 中的 stateCoverage 计算

**测试:** 确认 stale/selected 状态存在、manifest 显示 100%

---

### Task 5.2: Market Card 响应式断点 `[S]`

**验收:**
- `≥1024px`：3 列 grid
- `768-1023px`：2 列 grid
- `<768px`：1 列 stack

**文件:**
- Modify: `docs/designs/specs/prototypes/page-cross-market.html` — `.market-card-grid` 响应式

**Steps:**
1. 添加响应式断点：
   ```css
   @media (max-width: 1023px) {
     .market-card-grid { grid-template-columns: repeat(2, 1fr); }
   }
   @media (max-width: 767px) {
     .market-card-grid { grid-template-columns: 1fr; }
   }
   ```
2. 验证卡片内容在窄屏下不被截断

**测试:** 确认 3 个断点下 grid 列数正确

---

## Dependency Graph

```
Phase 1 (Data Liveness)
  1.1 数字平滑 ──┐
  1.2 Sparkline 脉冲 ──┤── 无依赖，可并行
  1.3 全局 LED ──────┘

Phase 2 (Signature Components)  ← 依赖 Phase 1 的动画基础设施
  2.1 Global Pulse 重设计 ← 依赖 1.2 (sparkline 脉冲)
  2.2 Decision Card 增强 ← 独立
  2.3 告警流式动画 ← 依赖 1.1 (data-tick keyframe 基础)

Phase 3 (Navigation)  ← 独立于 Phase 1-2
  3.1 Breadcrumb 导航

Phase 4 (Polish)  ← 依赖 Phase 1-2 完成
  4.1 表格行悬停 ← 独立
  4.2 Frosted Glass 差异化 ← 独立
  4.3 Sidebar Peek ← 独立
  4.4 空状态 CTA ← 独立

Phase 5 (Coverage)  ← 最后执行
  5.1 Home Coverage ← 独立
  5.2 响应式断点 ← 独立
```

## Complexity Summary

| Phase | Tasks | S | M | L | Total |
|---|---|---|---|---|---|
| Phase 1: Data Liveness | 3 | 2 | 1 | 0 | 3 |
| Phase 2: Signature Components | 3 | 0 | 2 | 1 | 3 |
| Phase 3: Navigation | 1 | 0 | 1 | 0 | 1 |
| Phase 4: Polish | 4 | 2 | 2 | 0 | 4 |
| Phase 5: Coverage | 2 | 1 | 1 | 0 | 2 |
| **Total** | **13** | **5** | **7** | **1** | **13** |

## Execution Order Recommendation

1. **Phase 1** (P0, 可 3 任务并行) → 数据生命感是最大 UX 差距
2. **Phase 2** (P1, 2.1 依赖 1.2) → 签名组件是第二个差距
3. **Phase 3** (P1, 独立) → 导航可与 Phase 2 并行
4. **Phase 4** (P2, 可 4 任务并行) → 精修
5. **Phase 5** (P3, 最后) → 覆盖率收尾

---

## Risks & Mitigations

| 风险 | 缓解 |
|---|---|
| `--font-size-20` 不在现有 token 档位 | 使用 `clamp()` 或直接在 `tokens-style.css` 页面级 token 中定义 |
| BulletGraph 在 Decision Card 内尺寸过大 | 使用 `--bar-height-sm: 3px` 紧凑模式 |
| Sidebar Peek 与现有 SidebarToggle 冲突 | Peek 仅在 collapsed 态触发，expanded 态不启用 |
| 告警动画在大量告警时性能问题 | 限制同时播放动画的告警数（最多 3 个） |
| Breadcrumb 数据维护成本 | 使用页面 meta 标签 + JS 自动提取 |
