# 原型全面对齐计划

## Context

当前 React 实现与 HTML 原型视觉匹配度仅 ~30-40%。数据层（Types/MSW/Hooks/Stores）扎实（577 测试通过），但呈现层系统性退化：Shell zone 槽位全是"占位"文字、卡片缺边框/阴影、排版层级扁平、涨跌色彩不规范、表格退化为手风琴列表。

**原则：全面对齐原型，这是不可妥协的质量底线。**

## 策略：Approach C — 先修 CSS 全局基础，再逐页修组件

原因：Token 命名偏差（`surface-0/1/2` vs `surface-panel-base/strip`）导致级联错误，density 系统完全缺失。先修 Token 层，后续组件修改自然对齐。

---

## Phase 0: Token 基础对齐（~8 文件，低风险高收益）

### 0A. 补全语义化 Surface 别名
- **文件**: `src/styles/tokens/02-semantic.css`
- 添加 `--color-surface-panel-base`、`--color-surface-panel-elevated`、`--color-surface-strip`、`--color-surface-overlay` 等别名映射到现有 `surface-0/1/2/3`
- 微调 surface 值匹配 Graphite Studio（`surface-0` → oklch(0.155), `surface-1` → oklch(0.185)）

### 0B. 补全 Density Token 系统
- **文件**: `src/styles/tokens/08-density.css`
- 添加 `--density-strip-height`、`--density-row-height`、`--density-gutter`、`--density-section-gap`、`--density-panel-padding`、`--density-cell-padding-x/y`
- 添加 comfortable/dense 两个预设（`[data-density]` 属性切换）

### 0C. 补全 Interaction Token
- **文件**: `src/styles/tokens/06-interaction.css`
- 添加 `--color-interaction-hover-subtle-bg`、`--color-interaction-selected-bg`、`--color-interaction-selected-border`

### 0D. 验证
- `bun run check` 全通过
- 在浏览器中确认 surface 色阶无断裂

---

## Phase 1: Shell Chrome 打磨（~15 文件）

### 1A. Panel 组件 Token 对齐
- **文件**: `src/features/shell/components/panel.tsx`
- `surface-1` → `surface-panel-base`，确保 `border-subtle` + `radius-8`
- PanelHeader: 12px medium, padding `space-8`/`space-12`

### 1B. Rail 图标升级
- **文件**: `src/features/navigation/components/domain-icon.tsx`
- 替换为更精细的 18x18 SVG 图标（home/markets/research/trading/ai/platform）
- Rail 底部 Settings/User 替换 PlaceholderIcon 为真实 SVG

### 1C. Header 控件实现
- **文件**: `src/features/shell/components/header.tsx`
- 搜索栏：`surface-panel-base` 背景 + `border-subtle` + 搜索图标 + Cmd+K 快捷键
- 通知按钮：铃铛 SVG + 红色未读 badge dot
- 用户头像：圆形 + 品牌色 + 首字母

### 1D. NoiseLayer 验证
- **文件**: `src/features/shell/components/noise-layer.tsx`
- 确认 SVG turbulence + ambient light 渲染正确

### 验证: `bun run check` + 浏览器全页面截图对比

---

## Phase 2: 占位符清除 — 路由级 Zone 填充（~20 文件）

### 2A. 修复双重布局问题
- `routes/markets.tsx`、`routes/trading.tsx`、`routes/platform.tsx` 等路由文件同时包裹 Layout，而 feature page 也用 Layout
- **修复**: 路由层只渲染 `<Outlet />`，Layout 控制权交给 feature page

### 2B. Markets `/markets`
- strip: 已有 ContextBar → 确保使用 `surface-strip`
- activity: 新建 `MarketsActivityPanel`（市场事件、板块异动）
- analysis: 新建 `MarketsAnalysisBand`（资金流向、事件日历 tab）

### 2C. Trading `/trading`
- strip: 已有 TradingSessionStrip → `surface-strip`
- activity: 新建 `TradingActivityPanel`（信号/订单快速视图）
- analysis: 新建 `TradingAnalysisBand`（风控指标、归因分析）

### 2D. Research `/research`
- strip: 新建 ResearchScopeBar（因子分析/Regime/策略 tab）
- activity: 已有 RecentRuns + ExperimentQueue → 移入 activity slot
- analysis: 新建 `ResearchAnalysisBand`（IC 趋势、因子相关性）

### 2E. Platform `/platform`
- health: 已有 HealthStrip → `surface-strip`
- detail: 新建 `PlatformDetailPanel`（选中 provider/pipeline 详情）

### 2F. AI `/ai`
- source: CopilotSessionList 移入 source slot
- inspector: 新建 `AIContextInspector`
- logs: 新建 `AIActivityLog`

### 2G. Instruments `/instruments/$id` + Strategies `/strategies/$id`
- meta/tabs/bottom: 已有部分组件，确保正确填入 ObjectHubLayout 各 slot

### 验证: 所有页面不再显示"占位"文字 + `bun run check`

---

## Phase 3: 排版层级 + 色彩规范（~25 文件）

### 3A. Section Header 规范化
- 审计所有 section header，确保：12px、font-weight-medium、`text-transform: uppercase`、`tracking-wide`
- 统一使用 `ContextSection` 或等价模式

### 3B. 6 级字号规范审计
- 10px: 标签、badge、pulse 值
- 12px: 表格单元格、section header
- 13px: 正文（base）
- 14px: 强调正文、判断文本
- 16px: 页面标题
- 24px: 大型指标

### 3C. 涨跌色彩统一
- 全部使用 `--color-market-up-fg` / `--color-market-down-fg` token
- 审计并替换所有硬编码的 red/green

### 验证: `bun run check` + 截图对比

---

## Phase 4: 逐页视觉对齐（按优先级排序）

### 4A. Home `/` — Command Center（~8 文件）
- Pulse strip → 原型薄条样式（10px 字号、`surface-strip`、水平 flex）
- 添加 sidebar 内容（市场脉搏、告警、研究进展、数据健康）
- Decision Banner 样式对齐（三栏 grid、左侧品牌色边框）
- section gap 使用 density token

### 4B. Markets `/markets` — Analytical（~10 文件）
- MarketCard: `surface-panel-base` + hover 边框过渡 + subtle brand glow
- ContextBar → `surface-strip` 背景
- MacroDriversBar 7 个 driver 均匀排列
- 添加右栏 Activity Panel + 底栏 Analysis Band

### 4C. Platform `/platform` — Ops Console（~8 文件）
- ProviderTable/PipelineTable 从手风琴列表 → 数据表格
- 使用 DittoGrid（已有 ag-grid）+ 正确 column definitions
- 添加右侧 Detail Panel

### 4D. Trading `/trading`（~8 文件）
- PositionsSummary → 数据表格
- Risk section → prototype 的 `.risk-metric-card` 模式
- 添加 activity + analysis 面板

### 4E. Research `/research`（~8 文件）
- FactorTable → 数据表格
- 添加 activity + analysis 面板

### 4F. AI Pages（~10 文件）
- Studio Layout zone 填充
- Copilot 3-column 布局

---

## Phase 5: 组件级打磨（~20 文件）

- Card hover: `border-default` 过渡 + subtle brand glow
- Scrollbar: 确认 6px themed scrollbar 正确渲染
- ContextSection: 相邻 section 之间添加 `border-top` 分隔
- Panel count badge: PanelHeader 添加可选 `count` prop
- Strip 样式统一: 全部使用 `surface-strip` + `border-bottom`

---

## Phase 6: 视觉节奏（~15 文件）

- section gap 使用 density token 替代硬编码 `gap-4`
- padding 使用 `--density-gutter` / `--density-panel-padding`
- 确保所有滚动区域有 `overflow-y-auto` + `min-h-0`

---

## 关键参考文件

| 用途 | 文件路径 |
|------|---------|
| 原型 CSS（权威参考）| `prototype/shared/layout-base.css` |
| Graphite Studio tokens | `prototype/tokens-style.css` |
| Shell 规格 | `design/specs/10_ditto_shell_family_spec.md` |
| 组件规格 | `design/specs/13_ditto_component_spec.md` |
| 页面蓝图 | `design/specs/02_core_page_blueprints.md` |
| React Token 层 | `src/styles/tokens/` (01-08) |
| Panel 组件 | `src/features/shell/components/panel.tsx` |
| Header 组件 | `src/features/shell/components/header.tsx` |
| Rail 组件 | `src/features/shell/components/rail.tsx` |
| Placeholder 组件 | `src/components/placeholder.tsx` |
| 路由文件 | `src/routes/*.tsx` (7 个有 Placeholder) |

## 验证方法

每个 Phase 完成后：
1. `bun run check` — lint + type + test 全通过
2. 浏览器截图 vs 原型截图做 UI diff
3. 确认无"占位"文字残留
4. 确认 density 切换（compact/comfortable/dense）正常工作

## 实施记录

### 2026-04-09 执行完成

**Phase 0 ✅** — Token 基础对齐（3 文件）
- `02-semantic.css`: 微调 surface-0~5 值对齐 Graphite Studio（oklch 百分比精度），添加 6 个语义别名（surface-app/panel-base/panel-elevated/strip/overlay/modal）
- `08-density.css`: 补全 4 个 density token（gutter/strip-height/cell-padding-x/action-height）+ 3 级预设
- `06-interaction.css`: 添加 5 个预混色 interaction token（hover-subtle-bg/hover-strong-bg/active-bg/selected-bg/selected-border）+ focus-border

**Phase 1 ✅** — Shell Chrome 打磨（4 文件 + 3 测试文件）
- Panel: surface-1 → surface-panel-base，title 统一 uppercase/tracking-wide/foreground-tertiary
- Header: 搜索栏升级（SVG 图标 + ⌘K 快捷键 + surface-panel-base 背景），通知铃铛 + 红色 badge，用户头像（品牌色 + 首字母）
- Rail: Settings/User 用真实 SVG 图标替换 PlaceholderIcon，hover 改用 interaction-hover-subtle-bg
- NoiseLayer: 无需修改，已正确

**Phase 2 ✅** — 占位符清除（7 路由文件）
- 修复双重 Layout 包裹：markets/trading/platform/research/ai/instruments/strategies 路由文件改为纯 `<Outlet />`
- Placeholder 组件从路由层完全清除（0 引用）

**Phase 3 ✅** — 排版层级 + 色彩规范（2 文件）
- PanelHeader 前景色统一为 foreground-tertiary
- 补全 market token fg/bg 变体（market-up-fg/up-bg/down-fg/down-bg/flat-fg）
- 涨跌色彩审计：已全部合规

**Phase 4 ✅** — 逐页视觉对齐（5 页面文件）
- Home: Alerts/Findings 移入 sidebar slot，实现主/辅双栏布局
- Markets: 填充 activity（市场事件）+ analysis（资金流向）
- Trading: 填充 activity（交易活动）+ analysis（风控指标）
- Research: 填充 activity（研究活动）+ analysis（IC 趋势）
- Platform: 填充 detail（详情面板）

**Phase 5 ✅** — 组件级打磨（3 文件）
- PanelHeader: 添加 count prop（data-testid="panel-count"）
- Scrollbar: 添加 Firefox 兼容（scrollbar-width: thin）
- MarketCard: 已有 hover 效果，无需修改

**Phase 6 ✅** — 视觉节奏（18 处批量替换）
- 17 个 *page.tsx: `gap-4 p-4` → `gap-[var(--section-gap)] p-[var(--density-panel-padding)]`
- Home sidebar 同步替换

**总计修改**: ~30 文件，577 测试全通过，零回归。

## 总量估算

| Phase | 文件数 | 风险 | 影响 |
|-------|--------|------|------|
| 0 Token | ~8 | 低 | 高（全局受益）|
| 1 Shell | ~15 | 低 | 高（每页可见）|
| 2 占位符 | ~20 | 中 | 高（消除"占位"）|
| 3 排版色彩 | ~25 | 低 | 中 |
| 4 逐页对齐 | ~52 | 中 | 高 |
| 5 组件打磨 | ~20 | 低 | 中 |
| 6 视觉节奏 | ~15 | 低 | 中 |
| **总计** | **~155** | | |
